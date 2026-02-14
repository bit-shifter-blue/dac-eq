# Streamlit Prototype - Conversational EQ Tuning

**Goal:** Build a working prototype that proves the end-to-end technology: conversational AI → EQ computation → device programming.

**Timeline:** 1-2 weeks part-time
**Output:** Local Python app that runs in browser, no packaging required
**Validation:** Does conversational EQ tuning actually work? Is it better than manual tuning?

---

## What This Proves

✅ **Claude API + tool_use works** with our existing handlers
✅ **eq-advisor reasoning** translates from MCP skill to API tools
✅ **Full pipeline works**: conversation → squiglink → autoeq → device write
✅ **User experience**: Is talking to Claude better than using sliders?
✅ **Cost model**: Real API usage data to estimate production costs

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  Streamlit Web UI (localhost:8501)         │
│  - Chat interface                           │
│  - Device connection status                 │
│  - FR curve visualization (optional)        │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│  Claude API (Haiku or Sonnet)              │
│  - eq-advisor system prompt                 │
│  - Tool definitions (6 tools)               │
│  - Streaming responses                      │
└──────────────────┬──────────────────────────┘
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
┌──────────────────┐  ┌──────────────────┐
│  squiglink tools │  │  autoeq tools    │
│  - search_iems   │  │  - compute_peq   │
│  - get_fr_data   │  │  - apply_peq     │
└──────────────────┘  └──────────────────┘
         │                   │
         └─────────┬─────────┘
                   ▼
         ┌──────────────────┐
         │  dac-eq tools    │
         │  - list_devices  │
         │  - write_peq     │
         │  - read_peq      │
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │  USB HID Device  │
         │  (Tanchjim/      │
         │   Qudelix/       │
         │   Moondrop)      │
         └──────────────────┘
```

---

## Implementation Phases

### Phase 1: Basic Streamlit Chat (Day 1-2)

**Files to create:**
- `streamlit_app.py` - Main application
- `requirements-streamlit.txt` - Dependencies

**Features:**
- Text input box for user messages
- Chat message history display
- Basic Claude API integration (no tools yet)
- Test with simple back-and-forth conversation

**Deliverable:** Can type "hello" and get Claude response in browser.

**Example code:**
```python
import streamlit as st
import anthropic

st.title("🎧 Conversational EQ Tuning")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Describe the sound you want..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Call Claude API (simplified - add tool_use in Phase 2)
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-haiku-4-5",
        messages=st.session_state.messages,
        max_tokens=1024
    )

    st.session_state.messages.append({
        "role": "assistant",
        "content": response.content[0].text
    })
    st.rerun()
```

### Phase 2: Tool Use Integration (Day 3-5)

**What to add:**
- Tool definitions matching our MCP tools
- Tool execution handlers
- Response streaming with tool calls visible

**Tools to implement (6 total):**

1. **search_iems** (squiglink)
   ```python
   {
       "name": "search_iems",
       "description": "Search for IEM models by name",
       "input_schema": {
           "type": "object",
           "properties": {
               "query": {"type": "string"}
           },
           "required": ["query"]
       }
   }
   ```

2. **get_fr_data** (squiglink)
3. **compute_peq** (autoeq)
4. **list_devices** (dac-eq)
5. **read_peq** (dac-eq)
6. **write_peq** (dac-eq)

**Tool execution pattern:**
```python
def execute_tool(tool_name, tool_input):
    """Execute a tool and return results"""
    if tool_name == "search_iems":
        # Import squiglink code
        from mcp.squiglink_mcp import server as squiglink
        result = squiglink.search_iems(**tool_input)
        return result

    elif tool_name == "get_fr_data":
        # ...

    elif tool_name == "write_peq":
        # Import and use dsp_devices handlers
        from dsp_devices import registry
        device = registry.get_connected_device()
        device.write_peq(...)
        return {"status": "success"}

    # ... etc
```

**Deliverable:** User can say "tune my Blessing 3 to Harman target" and see tool calls executing.

### Phase 3: eq-advisor Logic (Day 6-7)

**What to add:**
- Port eq-advisor skill prompt to system message
- Add reasoning framework (classify intent, determine approach)
- Multi-turn conversation support

**System prompt (adapted from skill):**
```python
EQ_ADVISOR_SYSTEM = """You are an expert audio tuning assistant...

When user describes desired sound:
1. Identify their IEM model
2. Fetch current FR data
3. Classify their intent (setting/mood/technical/relative)
4. Use tools to compute and apply EQ
5. Explain what you changed and why

Available tools:
- search_iems, get_fr_data (get measurements)
- compute_peq (calculate filters)
- list_devices, read_peq, write_peq (device control)
"""
```

**Deliverable:** Full conversational flow works: "make it warmer" → asks which IEM → fetches FR → computes EQ → writes to device.

### Phase 4: Device Connection UI (Day 8-9)

**What to add:**
- Sidebar with device status
- Connect/disconnect buttons
- Device selection dropdown (if multiple)
- Current EQ display (read from device)

**Example UI:**
```python
# Sidebar
with st.sidebar:
    st.header("🔌 Device Connection")

    if st.button("Scan for Devices"):
        devices = list_connected_devices()
        st.session_state.devices = devices

    if "devices" in st.session_state:
        device = st.selectbox("Select Device", st.session_state.devices)

        if st.button("Connect"):
            st.session_state.connected_device = connect(device)
            st.success(f"Connected to {device}")

    # Show current EQ
    if "connected_device" in st.session_state:
        st.subheader("Current EQ")
        profile = read_current_eq()
        st.json(profile)
```

**Deliverable:** Can see device status, connect, and view current settings without conversation.

### Phase 5: Visualization (Day 10-12, Optional)

**What to add:**
- FR curve plotting (before/after EQ)
- Filter visualization
- Interactive charts

**Libraries:**
- Plotly (interactive charts in Streamlit)
- matplotlib (static but simple)

**Example:**
```python
import plotly.graph_objects as go

# Plot FR curve
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=[p['freq'] for p in fr_data],
    y=[p['db'] for p in fr_data],
    name="Original FR"
))
fig.add_trace(go.Scatter(
    x=[p['freq'] for p in eq_fr_data],
    y=[p['db'] for p in eq_fr_data],
    name="After EQ"
))
st.plotly_chart(fig)
```

**Deliverable:** Can see visual representation of what EQ is doing.

### Phase 6: Polish & Testing (Day 13-14)

**What to add:**
- Error handling (device not connected, API errors)
- Loading states for tool execution
- Session persistence (save chat history)
- API key configuration (secrets.toml)
- Basic styling/branding

**Testing checklist:**
- [ ] Conversation starts without device connected
- [ ] Can connect device mid-conversation
- [ ] EQ writes successfully and persists
- [ ] Multiple EQ adjustments in one session work
- [ ] API errors are handled gracefully
- [ ] Works with Tanchjim, Qudelix, (Moondrop if available)

---

## File Structure

```
dac-eq/
├── streamlit_app.py              # Main Streamlit app
├── requirements-streamlit.txt    # New dependencies
├── .streamlit/
│   └── secrets.toml              # API key (gitignored)
├── streamlit_tools/
│   ├── __init__.py
│   ├── tool_definitions.py       # Claude API tool schemas
│   ├── tool_executor.py          # Tool execution logic
│   └── eq_advisor_prompt.py      # System prompt
├── dsp_devices/                  # Existing handlers (unchanged)
├── mcp/                          # Existing MCP servers (reuse code)
└── STREAMLIT_PROTOTYPE_PLAN.md   # This file
```

---

## Dependencies

Add to `requirements-streamlit.txt`:
```
streamlit>=1.30.0
anthropic>=0.18.0
plotly>=5.18.0
```

Existing dependencies (from `requirements.txt`):
```
hidapi>=0.14.0
scipy>=1.11.0
httpx>=0.25.0
```

---

## Running the Prototype

```bash
# Install dependencies
pip install -r requirements-streamlit.txt

# Set up API key
mkdir -p .streamlit
echo 'ANTHROPIC_API_KEY = "sk-ant-..."' > .streamlit/secrets.toml

# Run the app
streamlit run streamlit_app.py
```

Opens browser to `localhost:8501` automatically.

---

## Success Criteria

### Must Have
- ✅ User can describe desired sound in natural language
- ✅ Claude uses tools to fetch FR data and compute EQ
- ✅ EQ writes to connected device successfully
- ✅ Multi-turn conversation works (refine tuning)
- ✅ Works with at least one device (Tanchjim or Qudelix)

### Nice to Have
- ✅ Visual FR curves (before/after)
- ✅ Device status in sidebar
- ✅ Session history saved
- ✅ Works with all three device types

### Validation Metrics
- **API cost per session:** Track actual Claude API usage
- **User satisfaction:** Is conversation faster than manual tuning?
- **Success rate:** % of conversations that result in working EQ
- **Iteration count:** How many back-and-forth exchanges typical?

---

## Cost Estimation (for 100 test sessions)

| Model | Tokens/session | Cost/session | 100 sessions |
|-------|----------------|--------------|--------------|
| Haiku | ~5K input, ~1K output | $0.01-0.02 | **$1-2** |
| Sonnet | ~5K input, ~1K output | $0.05-0.10 | $5-10 |

**Recommendation:** Use Haiku for prototype. It's capable enough for eq-advisor reasoning and 50x cheaper than Sonnet.

---

## Risks & Mitigations

### Risk 1: Claude API tool_use is unfamiliar
**Mitigation:** Start with simple test (Phase 1) before adding tools. Anthropic docs are excellent.

### Risk 2: Streamlit state management is tricky
**Mitigation:** Use `st.session_state` for everything. Keep it simple - no complex caching.

### Risk 3: Tool execution is slow (USB HID writes take time)
**Mitigation:** Add loading spinners. Consider async tool execution in later iteration.

### Risk 4: Conversation doesn't feel natural
**Mitigation:** Iterate on system prompt. Test with real users (yourself first).

---

## Next Steps After Prototype

If prototype validates the concept:

### Option A: Productize as Downloadable App
- Package with PyInstaller or py2app
- Add payment integration (Gumroad)
- Polish UI (replace Streamlit with native GUI)
- Timeline: 6-8 weeks

### Option B: Keep as Developer Tool
- Distribute as open-source Python app
- User runs locally with own API key
- No payment needed, community-driven
- Timeline: 2-3 weeks for docs/packaging

### Option C: Pivot to API Service
- Remove device handlers, focus on EQ computation
- Ship as web API: "send me your IEM model + desired sound → get back filter JSON"
- Users apply filters with devicePEQ or manufacturer apps
- Timeline: 3-4 weeks

---

## Decision Points

**After Phase 2 (Day 5):** Does tool_use work smoothly? If not, reassess approach.

**After Phase 3 (Day 7):** Is conversational tuning actually better than sliders? If not, consider stopping.

**After Phase 6 (Day 14):** Is this worth productizing? Check API costs, user feedback, technical feasibility.

---

## Conclusion

This prototype answers the core question: **Is AI-powered conversational EQ tuning valuable?**

- **Low risk:** 1-2 weeks investment, reuses existing code
- **High signal:** Proves (or disproves) the novel part of your idea
- **No commitment:** If it doesn't work, you learned something. If it does, you have a path to production.

Build this first. Everything else (GUI, payments, distribution) can wait until you know the core concept works.
