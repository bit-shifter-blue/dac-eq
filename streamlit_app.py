"""
EQ Advisor - Conversational IEM Tuning
Phase 2: Tool use integration
"""

import streamlit as st
import anthropic
import os
import json

# Import tools
from tools import TOOLS, execute_tool

# Load config from TOML
try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # Fallback for older Python

with open("config.toml", "rb") as f:
    config = tomllib.load(f)

# Page config
st.set_page_config(
    page_title=config["ui"]["page_title"],
    page_icon=config["ui"]["page_icon"],
    layout="wide"
)

st.title(f"{config['ui']['page_icon']} {config['ui']['page_title']} - Conversational IEM Tuning")
st.caption("Describe the sound you want, and I'll help tune your IEMs")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Describe the sound you want..."):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)

    # Get Claude response with tool use
    with st.chat_message("assistant"):
        try:
            # Get API key from secrets or environment
            api_key = st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

            if not api_key:
                st.error("⚠️ ANTHROPIC_API_KEY not found. Please set it in .streamlit/secrets.toml")
                st.stop()

            client = anthropic.Anthropic(api_key=api_key)

            # Tool use loop - keep calling until we get a text response
            response_text = ""
            tool_results = []

            with st.status("Thinking...", expanded=True) as status:
                while True:
                    # Call Claude API with tools
                    response = client.messages.create(
                        model=config["model"]["id"],
                        max_tokens=config["model"]["max_tokens"],
                        tools=TOOLS,
                        messages=st.session_state.messages
                    )

                    # Check stop reason
                    if response.stop_reason == "end_turn":
                        # Extract final text response
                        for block in response.content:
                            if block.type == "text":
                                response_text += block.text
                        break

                    elif response.stop_reason == "tool_use":
                        # Process tool calls
                        for block in response.content:
                            if block.type == "tool_use":
                                tool_name = block.name
                                tool_input = block.input

                                # Display tool call
                                st.write(f"🔧 **{tool_name}**")
                                st.json(tool_input)

                                # Execute tool
                                tool_result = execute_tool(tool_name, tool_input)

                                # Store for next API call
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": json.dumps(tool_result)
                                })

                        # Add assistant message with tool use
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": response.content
                        })

                        # Add tool results
                        st.session_state.messages.append({
                            "role": "user",
                            "content": tool_results
                        })

                        tool_results = []  # Reset for next iteration

                    else:
                        # Unexpected stop reason
                        st.error(f"Unexpected stop reason: {response.stop_reason}")
                        break

                status.update(label="Complete!", state="complete", expanded=False)

            # Display final response
            if response_text:
                st.markdown(response_text)

                # Add to chat history
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response_text
                })

        except Exception as e:
            st.error(f"Error: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

# Sidebar with info
with st.sidebar:
    st.header("ℹ️ About")
    st.write("**EQ Advisor** helps you tune your IEMs through natural conversation.")

    st.divider()

    st.subheader("Status")
    st.write("**Phase:** 2 (Tool Integration)")
    st.write(f"**Tools:** {len(TOOLS)} available")
    model_id = config["model"]["id"]
    st.write(f"**Model:** {model_id.split('-')[1].title()} {model_id.split('-')[2]}")

    # Show available tools
    with st.expander("Available Tools"):
        for tool in TOOLS:
            st.write(f"• **{tool['name']}** - {tool['description'][:60]}...")

    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.rerun()
