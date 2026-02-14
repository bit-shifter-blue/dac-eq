"""
AutoEQ wrapper for computing optimal PEQ filters from FR data.
"""
import os
from pathlib import Path
from typing import Optional

import numpy as np

from autoeq.frequency_response import FrequencyResponse


# Project root (eq-advisor/)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Targets directory (persistent cache, not temp)
TARGETS_DIR = PROJECT_ROOT / "cache" / "targets"

# Default device constraints
DEFAULT_CONSTRAINTS = {
    "max_filters": 5,
    "gain_range": [-12, 12],
    "q_range": [0.5, 10],
    "freq_range": [20, 20000],
    "filter_types": ["PK", "LSQ", "HSQ"]
}


def list_available_targets() -> list[str]:
    """List available target curve names."""
    if not TARGETS_DIR.exists():
        return []
    targets = []
    for f in TARGETS_DIR.glob("*.csv"):
        targets.append(f.stem)
    return sorted(targets)


def load_target(name: str) -> FrequencyResponse:
    """Load a target curve by name."""
    target_path = TARGETS_DIR / f"{name}.csv"
    if not target_path.exists():
        raise ValueError(f"Target '{name}' not found. Available: {list_available_targets()}")
    return FrequencyResponse.read_csv(str(target_path))


def export_target(name: str) -> list[dict]:
    """Export a target curve as frequency/dB pairs."""
    target = load_target(name)
    return [
        {"freq": float(f), "db": float(d)}
        for f, d in zip(target.frequency, target.raw)
    ]


def fr_data_to_frequency_response(fr_data: list[dict], name: str = "measurement") -> FrequencyResponse:
    """Convert squig.link format FR data to FrequencyResponse object."""
    freqs = np.array([p["freq"] for p in fr_data])
    dbs = np.array([p["db"] for p in fr_data])
    return FrequencyResponse(name=name, frequency=freqs, raw=dbs)


def build_peq_config(constraints: dict) -> dict:
    """
    Build AutoEQ PEQ config from device constraints.

    AutoEQ expects a dict with 'filters' key containing filter configs, each with:
    - type: filter type (LOW_SHELF, PEAKING, HIGH_SHELF)
    - min_fc, max_fc: frequency range
    - min_q, max_q: Q factor range
    - min_gain, max_gain: gain range
    """
    max_filters = constraints.get("max_filters", DEFAULT_CONSTRAINTS["max_filters"])
    freq_range = constraints.get("freq_range", DEFAULT_CONSTRAINTS["freq_range"])
    q_range = constraints.get("q_range", DEFAULT_CONSTRAINTS["q_range"])
    gain_range = constraints.get("gain_range", DEFAULT_CONSTRAINTS["gain_range"])
    filter_types = constraints.get("filter_types", DEFAULT_CONSTRAINTS["filter_types"])

    filters = []
    for i in range(max_filters):
        # First filter can be low shelf if supported
        if i == 0 and "LSQ" in filter_types:
            filters.append({
                "type": "LOW_SHELF",
                "min_fc": freq_range[0],
                "max_fc": min(500, freq_range[1]),
                "min_q": q_range[0],
                "max_q": q_range[1],
                "min_gain": gain_range[0],
                "max_gain": gain_range[1]
            })
        # Last filter can be high shelf if supported
        elif i == max_filters - 1 and "HSQ" in filter_types:
            filters.append({
                "type": "HIGH_SHELF",
                "min_fc": max(2000, freq_range[0]),
                "max_fc": freq_range[1],
                "min_q": q_range[0],
                "max_q": q_range[1],
                "min_gain": gain_range[0],
                "max_gain": gain_range[1]
            })
        else:
            filters.append({
                "type": "PEAKING",
                "min_fc": freq_range[0],
                "max_fc": freq_range[1],
                "min_q": q_range[0],
                "max_q": q_range[1],
                "min_gain": gain_range[0],
                "max_gain": gain_range[1]
            })

    return {"filters": filters}


def calculate_pregain(filters: list[dict]) -> float:
    """Calculate pregain to avoid clipping (negative of max positive gain)."""
    max_boost = 0.0
    for f in filters:
        if f.get("gain", 0) > max_boost:
            max_boost = f["gain"]
    # Add 0.5dB headroom
    return round(-max_boost - 0.5, 1) if max_boost > 0 else 0.0


def convert_filter_type(autoeq_type: str) -> str:
    """Convert AutoEQ filter type to device format."""
    type_map = {
        "PEAKING": "PK",
        "LOW_SHELF": "LSQ",
        "HIGH_SHELF": "HSQ",
        "PK": "PK",
        "LSQ": "LSQ",
        "HSQ": "HSQ"
    }
    return type_map.get(autoeq_type, "PK")


def enforce_constraints(filters: list[dict], constraints: dict) -> list[dict]:
    """Enforce device constraints on filter parameters."""
    freq_min, freq_max = constraints.get("freq_range", DEFAULT_CONSTRAINTS["freq_range"])
    gain_min, gain_max = constraints.get("gain_range", DEFAULT_CONSTRAINTS["gain_range"])
    q_min, q_max = constraints.get("q_range", DEFAULT_CONSTRAINTS["q_range"])
    max_filters = constraints.get("max_filters", DEFAULT_CONSTRAINTS["max_filters"])

    result = []
    for f in filters:
        freq = f.get("freq", f.get("fc", 1000))
        gain = f.get("gain", 0)
        q = f.get("q", 1.0)
        ftype = convert_filter_type(f.get("type", "PK"))

        # Skip filters outside frequency range
        if freq < freq_min or freq > freq_max:
            continue

        # Clamp gain and Q
        gain = max(gain_min, min(gain_max, gain))
        q = max(q_min, min(q_max, q))

        # Skip negligible filters
        if abs(gain) < 0.3:
            continue

        result.append({
            "freq": round(freq, 1),
            "gain": round(gain, 1),
            "q": round(q, 2),
            "type": ftype
        })

        if len(result) >= max_filters:
            break

    return result


def compute_peq(
    fr_data: list[dict],
    target_name: str,
    constraints: Optional[dict] = None
) -> dict:
    """
    Compute optimal PEQ filters to match FR data to target curve.

    Args:
        fr_data: List of {"freq": Hz, "db": dB} from squig.link format
        target_name: Name of target curve (e.g., "harman_ie_2019")
        constraints: Device constraints dict with max_filters, gain_range, etc.

    Returns:
        dict with "pregain" (float) and "filters" (list of filter dicts)
    """
    if constraints is None:
        constraints = DEFAULT_CONSTRAINTS.copy()

    # Convert input data to FrequencyResponse
    fr = fr_data_to_frequency_response(fr_data)

    # Load target curve
    target = load_target(target_name)

    # Build PEQ config from constraints
    peq_config = build_peq_config(constraints)

    # Process the frequency response
    fr.interpolate()
    fr.center()
    fr.compensate(target)
    fr.smoothen(window_size=1/3)
    fr.equalize()  # Compute equalization curve from error

    # Run the optimizer
    # AutoEQ's optimize_parametric_eq returns a list of PEQ objects
    try:
        peq_objects = fr.optimize_parametric_eq(
            [peq_config],  # Pass as list of configs
            fs=48000,
            max_time=5.0  # Limit optimization time
        )

        # Extract filters from PEQ objects
        peq_filters = []
        for peq in peq_objects:
            peq_dict = peq.to_dict()
            for f in peq_dict.get('filters', []):
                peq_filters.append({
                    "fc": f['fc'],
                    "gain": f['gain'],
                    "q": f['q'],
                    "type": f['type']
                })
    except Exception as e:
        # Fallback: simple peak-finding approach
        peq_filters = []
        error = fr.equalization if hasattr(fr, 'equalization') and len(fr.equalization) > 0 else -fr.error
        if len(error) > 0:
            # Find the N largest deviations
            max_filters = constraints.get("max_filters", 5)
            for _ in range(max_filters):
                idx = np.argmax(np.abs(error))
                if abs(error[idx]) < 0.5:  # Stop if remaining error is small
                    break
                peq_filters.append({
                    "fc": fr.frequency[idx],
                    "gain": -error[idx],
                    "q": 1.5,
                    "type": "PEAKING"
                })
                # Zero out nearby region to find next peak
                width = max(1, len(error) // 20)
                start = max(0, idx - width)
                end = min(len(error), idx + width)
                error[start:end] = 0

    # Convert and enforce constraints
    filters = enforce_constraints(peq_filters, constraints)

    # Calculate pregain
    pregain = calculate_pregain(filters)

    return {
        "pregain": pregain,
        "filters": filters
    }


def export_fr(fr_data: list[dict]) -> str:
    """Export FR data as tab-separated text (squig.link format)."""
    lines = []
    for point in fr_data:
        lines.append(f"{point['freq']}\t{point['db']}")
    return "\n".join(lines)


def export_peq(pregain: float, filters: list[dict]) -> str:
    """Export PEQ as JSON string (compatible with write_peq)."""
    import json
    return json.dumps({
        "pregain": pregain,
        "filters": filters
    }, indent=2)


def apply_peq_to_fr(fr_data: list[dict], filters: list[dict], pregain: float = 0.0) -> list[dict]:
    """
    Apply PEQ filters to FR data and return the resulting FR curve.

    Args:
        fr_data: List of {"freq": Hz, "db": dB} from squig.link format
        filters: List of filter dicts with freq, gain, q, type
        pregain: Pregain in dB

    Returns:
        list of {"freq": Hz, "db": dB} after EQ applied
    """
    import math

    frequencies = [p["freq"] for p in fr_data]
    result = [p["db"] for p in fr_data]

    # Apply each filter sequentially
    for f in filters:
        if f.get("gain", 0) == 0:  # Skip disabled filters
            continue

        freq = f["freq"]
        gain = f["gain"]
        q = f["q"]
        ftype = f["type"]

        # Biquad coefficients computation
        fs = 48000.0
        w0 = 2 * math.pi * freq / fs
        sin_w0 = math.sin(w0)
        cos_w0 = math.cos(w0)
        alpha = sin_w0 / (2 * q)
        A = 10 ** (gain / 40.0)

        if ftype == "PK":
            b0 = 1 + alpha * A
            b1 = -2 * cos_w0
            b2 = 1 - alpha * A
            a0 = 1 + alpha / A
            a1 = -2 * cos_w0
            a2 = 1 - alpha / A
        elif ftype == "LSQ":
            sqrt_A = math.sqrt(A)
            b0 = A * ((A + 1) - (A - 1) * cos_w0 + 2 * sqrt_A * alpha)
            b1 = 2 * A * ((A - 1) - (A + 1) * cos_w0)
            b2 = A * ((A + 1) - (A - 1) * cos_w0 - 2 * sqrt_A * alpha)
            a0 = (A + 1) + (A - 1) * cos_w0 + 2 * sqrt_A * alpha
            a1 = -2 * ((A - 1) + (A + 1) * cos_w0)
            a2 = (A + 1) + (A - 1) * cos_w0 - 2 * sqrt_A * alpha
        elif ftype == "HSQ":
            sqrt_A = math.sqrt(A)
            b0 = A * ((A + 1) + (A - 1) * cos_w0 + 2 * sqrt_A * alpha)
            b1 = -2 * A * ((A - 1) + (A + 1) * cos_w0)
            b2 = A * ((A + 1) + (A - 1) * cos_w0 - 2 * sqrt_A * alpha)
            a0 = (A + 1) - (A - 1) * cos_w0 + 2 * sqrt_A * alpha
            a1 = 2 * ((A - 1) - (A + 1) * cos_w0)
            a2 = (A + 1) - (A - 1) * cos_w0 - 2 * sqrt_A * alpha
        else:
            continue

        # Normalize
        b0 /= a0
        b1 /= a0
        b2 /= a0
        a1 /= a0
        a2 /= a0

        # Compute filter response at each frequency
        for i, freq_point in enumerate(frequencies):
            w = 2 * math.pi * freq_point / fs
            cos_w = math.cos(w)
            sin_w = math.sin(w)
            cos_2w = math.cos(2 * w)
            sin_2w = math.sin(2 * w)

            # Complex numerator: b0 + b1*e^(-jw) + b2*e^(-j2w)
            num_real = b0 + b1 * cos_w + b2 * cos_2w
            num_imag = -b1 * sin_w - b2 * sin_2w

            # Complex denominator: 1 + a1*e^(-jw) + a2*e^(-j2w)
            den_real = 1 + a1 * cos_w + a2 * cos_2w
            den_imag = -a1 * sin_w - a2 * sin_2w

            # Complex division
            den_mag_sq = den_real**2 + den_imag**2 + 1e-10
            real = (num_real * den_real + num_imag * den_imag) / den_mag_sq
            imag = (num_imag * den_real - num_real * den_imag) / den_mag_sq

            mag = math.sqrt(real**2 + imag**2)
            mag_db = 20 * math.log10(mag + 1e-10)
            result[i] += mag_db

    # Apply pregain
    result = [r + pregain for r in result]

    return [{"freq": frequencies[i], "db": round(result[i], 2)} for i in range(len(frequencies))]


def compute_peq_from_fr(
    fr_data_measured: list[dict],
    fr_data_target: list[dict],
    constraints: Optional[dict] = None
) -> dict:
    """
    Compute optimal PEQ filters to match measured FR to target FR.

    IMPORTANT: Use complete FR datasets (all measurement points) for best results.
    Sparse sampling loses critical frequency information and degrades optimization quality.
    For example, sampling 16 points from 479 total points (96% data loss) will result
    in poor filter accuracy. Always pass the full dataset when available.

    Args:
        fr_data_measured: List of {"freq": Hz, "db": dB} of measured FR. Use complete dataset.
        fr_data_target: List of {"freq": Hz, "db": dB} of target FR. Use complete dataset.
        constraints: Device constraints dict

    Returns:
        dict with "pregain" (float) and "filters" (list of filter dicts)
    """
    if constraints is None:
        constraints = DEFAULT_CONSTRAINTS.copy()

    # Convert to FrequencyResponse objects
    fr_measured = fr_data_to_frequency_response(fr_data_measured, name="measured")
    fr_target = fr_data_to_frequency_response(fr_data_target, name="target")

    # Build PEQ config
    peq_config = build_peq_config(constraints)

    # Process the frequency response
    fr_measured.interpolate()
    fr_measured.center()

    # Manually set the target instead of loading from file
    fr_target.interpolate()
    fr_measured.target = fr_target.raw

    # Compensate to target and compute equalization
    fr_measured.compensate(fr_target)
    fr_measured.smoothen(window_size=1/3)
    fr_measured.equalize()

    # Run the optimizer
    try:
        peq_objects = fr_measured.optimize_parametric_eq(
            [peq_config],
            fs=48000,
            max_time=5.0
        )

        peq_filters = []
        for peq in peq_objects:
            peq_dict = peq.to_dict()
            for f in peq_dict.get('filters', []):
                peq_filters.append({
                    "fc": f['fc'],
                    "gain": f['gain'],
                    "q": f['q'],
                    "type": f['type']
                })
    except Exception as e:
        # Fallback: simple peak-finding approach
        peq_filters = []
        error = fr_measured.equalization if hasattr(fr_measured, 'equalization') and len(fr_measured.equalization) > 0 else -fr_measured.error
        if len(error) > 0:
            max_filters = constraints.get("max_filters", 5)
            for _ in range(max_filters):
                idx = np.argmax(np.abs(error))
                if abs(error[idx]) < 0.5:
                    break
                peq_filters.append({
                    "fc": fr_measured.frequency[idx],
                    "gain": -error[idx],
                    "q": 1.5,
                    "type": "PEAKING"
                })
                width = max(1, len(error) // 20)
                start = max(0, idx - width)
                end = min(len(error), idx + width)
                error[start:end] = 0

    filters = enforce_constraints(peq_filters, constraints)
    pregain = calculate_pregain(filters)

    return {
        "pregain": pregain,
        "filters": filters
    }


def interpolate_fr(fr_data: list[dict], target_points: int = 1000) -> list[dict]:
    """
    Interpolate/smooth FR data to a target number of points.

    Args:
        fr_data: List of {"freq": Hz, "db": dB}
        target_points: Number of points in output (default 1000)

    Returns:
        Interpolated FR data
    """
    fr = fr_data_to_frequency_response(fr_data, name="interpolated")
    fr.interpolate()

    # Return as FR data format
    return [
        {"freq": float(f), "db": float(d)}
        for f, d in zip(fr.frequency, fr.raw)
    ]


def compare_fr_curves(fr_data1: list[dict], fr_data2: list[dict]) -> dict:
    """
    Compare two FR curves and return statistics.

    Args:
        fr_data1: First FR curve
        fr_data2: Second FR curve

    Returns:
        dict with comparison stats (error, rmse, max_diff, etc.)
    """
    fr1 = fr_data_to_frequency_response(fr_data1, name="curve1")
    fr2 = fr_data_to_frequency_response(fr_data2, name="curve2")

    fr1.interpolate()
    fr2.interpolate()

    # Normalize: align by mean dB so we compare shape, not absolute SPL
    offset = float(np.mean(fr1.raw) - np.mean(fr2.raw))
    error = (fr1.raw - offset) - fr2.raw

    rmse = float(np.sqrt(np.mean(error**2)))
    max_diff = float(np.max(np.abs(error)))
    min_diff = float(np.min(error))
    max_positive = float(np.max(error))

    # Find regions of biggest difference
    normalized_raw1 = fr1.raw - offset
    top_3_indices = np.argsort(np.abs(error))[-3:][::-1]
    peak_differences = [
        {
            "freq": float(fr1.frequency[i]),
            "curve1_db": float(normalized_raw1[i]),
            "curve2_db": float(fr2.raw[i]),
            "diff_db": float(error[i])
        }
        for i in top_3_indices
    ]

    return {
        "offset_applied": offset,
        "rmse": rmse,
        "max_diff": max_diff,
        "min_diff": min_diff,
        "max_positive_diff": max_positive,
        "peak_differences": peak_differences
    }
