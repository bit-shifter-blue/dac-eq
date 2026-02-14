# Moondrop DSP Test Fixtures

This directory contains test EQ profiles for Moondrop DSP devices (FreeDSP Pro/Mini, Rays, Marigold, MAY DSP).

## Test Profiles

### `flat_eq.json`
Neutral profile with 8 filters all set to 0 gain. Useful for:
- Testing device communication
- Verifying round-trip read/write consistency
- Resetting device to flat response

### `bass_boost.json`
Single low-shelf filter for bass enhancement. Tests:
- LSQ (low-shelf) filter type
- Moderate gain (+6 dB)
- Pregain compensation (-3 dB)

### `treble_adjust.json`
Single high-shelf filter for treble reduction. Tests:
- HSQ (high-shelf) filter type
- Negative gain (-4 dB)
- Pregain compensation (-2 dB)

### `comprehensive_test.json`
Complex profile using all 8 filter slots with variety of parameters. Tests:
- All three filter types (LSQ, PK, HSQ)
- Various Q values (0.7 - 3.0)
- Positive and negative gains
- Full pregain range (-6 dB)
- Edge cases and limits

## Testing Workflow

### 1. Device Detection
```bash
python cli.py --list --debug
```
Verify Moondrop device is detected with correct handler.

### 2. Read Current Settings
```bash
python cli.py --read --json moondrop_current.json --debug
```
Capture current device settings.

### 3. Write Test Profile
```bash
python cli.py --json eq/moondrop/flat_eq.json --debug
```
Write a test profile to device.

### 4. Round-Trip Test
```bash
# Write profile
python cli.py --json eq/moondrop/comprehensive_test.json

# Read it back
python cli.py --read --json moondrop_readback.json

# Compare (values should match within rounding tolerance)
diff eq/moondrop/comprehensive_test.json moondrop_readback.json
```

### 5. Edge Case Testing
- Maximum gain: ±20 dB
- Minimum Q: 0.1
- Maximum Q: 10.0
- All 8 filters active
- Pregain limits: -12 to +12 dB

## Expected Behavior

### Successful Write
- Device should accept all filter values
- Settings should persist after power cycle
- Audio output should reflect EQ changes

### Potential Issues
- **Biquad overflow**: Extreme Q or gain values may produce large coefficients
- **Device-specific limits**: Some models (Marigold) may not support LSQ/HSQ
- **Precision**: Read values may differ slightly due to fixed-point rounding

## Moondrop Protocol Notes

- **Sample Rate**: 96 kHz (assumed for biquad calculation)
- **Biquad Scaling**: 2^30 (1,073,741,824)
- **Value Scaling**: 256x for gain/Q
- **Filter Types**: PK=2, LSQ=1, HSQ=3 (different from Tanchjim!)
- **Packet Size**: 63 bytes (write), 64 bytes (read response)
- **Enable Sequence**: Write → Enable → Save to Flash
