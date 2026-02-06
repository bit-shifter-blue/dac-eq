---
name: eq-advisor
description: Structured reasoning framework for IEM EQ adjustments. Use when the user wants to change sound presentation, tune their IEMs, adjust frequency response, or achieve a specific sound signature or listening experience. ALWAYS invoke this skill FIRST before using any dac-eq MCP tools directly.
allowed-tools: mcp__squiglink__*, mcp__autoeq__*, mcp__dac-eq__*, AskUserQuestion, Read, Write
---

# IEM EQ Advisor - Structured Reasoning Framework

When the user wants to adjust the sound of their IEMs, follow this structured reasoning process before taking any action.

## Phase 1: Gather Required Context

You must determine three critical pieces of information. Check the conversation history first - if any are missing, ask the user.

### 1. What IEM is the user listening on?

**Check conversation history first.** Look for:
- Explicit mentions of IEM model names
- Previous references to devices or headphones
- Context from earlier in the session

**If not found in context:** Ask the user what IEM they're using, or offer to search available IEMs via squiglink MCP.

**Once determined:** Use `mcp__squiglink__search_iems` to find the model and fetch stock FR data with `mcp__squiglink__get_fr_data`.

### 2. What is the stock frequency response for that IEM?

After identifying the IEM, retrieve its baseline FR measurement from squiglink. This is your starting point.

**Note:** Some IEMs may have multiple measurements (different databases, different units). If multiple exist, inform the user and either:
- Use the most authoritative source (Crinacle preferred)
- Ask the user which measurement to use

### 3. What defines the desired sound profile?

This is the most nuanced part. The user's request can take many forms - you must classify and clarify their intent.

## Phase 2: Classify User Intent

Before proceeding, understand what type of request this is:

### 3A. Request Type - What is the user describing?

Determine which category their request falls into:

**Type A: Setting/Context-Based**
- "I want EQ for gaming"
- "Make it better for jazz"
- "Tune for movie watching"
- "I listen in noisy environments"

**Type B: Mood/Subjective Quality**
- "Make it warmer"
- "I want more energy"
- "Less fatiguing"
- "More fun/exciting sound"

**Type C: Direct Technical Specification**
- "Apply Harman IE 2019 target"
- "Boost bass by 3dB"
- "Roll off treble above 8kHz"
- "Match the Blessing 3 tuning"

**Type D: Relative Adjustment**
- "More bass than I have now"
- "Less harsh than stock"
- "Similar to what I have but with less treble"

### 3B. Reference Frame - Adjustment vs Desired State?

Determine if the user is:

**Adjustment Mode (Relative):**
- Describing changes to what they *currently hear*
- "More/less/different than now"
- Requires reading current device EQ state first via `mcp__dac-eq__read_peq`

**Desired State Mode (Absolute):**
- Describing a separate end goal
- "I want it to sound like X"
- "Apply target curve Y"
- Start from stock FR, not current EQ

**If unclear:** Ask the user with structured options using `AskUserQuestion`.

## Phase 3: Clarification Questions

If the user's intent is ambiguous (common for Type A, B, or D requests), ask clarifying questions:

**For Setting/Context-Based (Type A):**
- What aspect of the sound matters most for this use case? (bass impact, vocal clarity, soundstage, etc.)
- Any specific problem with the current sound for this use case?

**For Mood/Subjective (Type B):**
- Translate subjective terms to technical adjustments by asking:
  - "By 'warmer', do you mean more bass, less treble, or both?"
  - "For 'energy', are you looking for more upper midrange presence, treble sparkle, or both?"

**For Relative Adjustments (Type D):**
- Should I read your current device EQ first, or start from the stock IEM tuning?
- How much of a change? (subtle, moderate, significant)

Use `AskUserQuestion` tool with structured options for these clarifications.

## Phase 4: Translation to Technical Plan

Once you have complete context, translate the user's goal into a technical plan:

**State your understanding:**
1. "You're using [IEM model]"
2. "The stock FR shows [brief characterization - e.g., 'neutral with slight bass boost']"
3. "You want to [clear statement of goal in technical terms]"
4. "This means adjusting [specific frequency regions] to achieve [outcome]"

**Then outline your approach:**
- Target curve to use (from autoeq MCP, or custom)
- Expected changes (which frequencies will be boosted/cut)
- Pregain requirements (to prevent clipping)
- Number of filters needed

**Ask for confirmation** before proceeding: "Does this match what you're looking for?"

## Phase 5: Execute

Once confirmed, invoke the appropriate tools to achieve the desired profile:

1. **Compute PEQ filters:**
   - Use `mcp__autoeq__compute_peq` with the stock FR data and target curve
   - Query device constraints via `mcp__dac-eq__get_device_capabilities` to respect filter count and type limits

2. **Review generated filters:**
   - Show the user the computed pregain and filter settings
   - Explain what each filter is doing in plain language

3. **Apply to device:**
   - Use `mcp__dac-eq__write_peq` to write to the connected device
   - Confirm successful write

4. **Provide listening guidance:**
   - Suggest a test track or listening scenario
   - Explain what they should notice
   - Offer to iterate if needed

## Important Notes

- **Always reason through all phases before taking action.** Do not skip ahead to execution.
- **Make your reasoning visible to the user.** Show your thought process at each step.
- **When in doubt, ask.** Use AskUserQuestion for structured clarification.
- **Read device state when in Adjustment Mode.** Use `mcp__dac-eq__read_peq` before computing new filters.
- **Respect device constraints.** Query capabilities via `mcp__dac-eq__get_device_capabilities` for filter count and type limits.
- **Iterate if needed.** After applying, offer to refine based on user feedback.

## Example Invocations

**Explicit:** `/eq-advisor "Make it warmer for late-night listening"`

**Automatic triggers:**
- "Can you EQ my IEMs for more bass?"
- "I want to tune these for classical music"
- "Apply Harman target to my Blessing 3"
- "Make the treble less harsh"
- "I want more mellow sound"
- "Make it warmer"
- "Make it brighter"
- "More bass"
- "Less treble"
- "EQ for [any genre]" (jazz, folk, metal, classical, etc.)
