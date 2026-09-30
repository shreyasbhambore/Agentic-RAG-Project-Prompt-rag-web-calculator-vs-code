"""Authenticated Streamlit chat, history, sources, and logout interface."""

from typing import Any

import requests
import streamlit as st

from api_client import (
    get_conversation,
    get_current_user,
    get_health,
    list_conversations,
    login,
    register,
    stream_chat,
)


def _clear_authentication() -> None:
    for key in (
        "access_token",
        "refresh_token",
        "current_user",
        "conversation_id",
        "chat_messages",
        "history_selection",
        "loaded_conversation_id",
        "conversations",
    ):
        st.session_state.pop(key, None)


def _request_error(error: requests.RequestException) -> str:
    response = getattr(error, "response", None)
    if response is not None:
        try:
            detail = response.json().get("detail")
            if isinstance(detail, str):
                return detail
        except (ValueError, AttributeError):
            pass
    return "Could not reach the backend. Check that FastAPI is running and try again."


def _load_conversation(access_token: str, conversation_id: str) -> None:
    conversation = get_conversation(access_token, conversation_id)
    messages = conversation.get("messages", [])
    loaded_messages: list[dict[str, Any]] = []
    for item in messages:
        if (
            not isinstance(item, dict)
            or item.get("role") not in {"user", "assistant"}
            or not isinstance(item.get("content"), str)
        ):
            continue
        sources = item.get("sources")
        loaded_messages.append(
            {
                "role": item["role"],
                "content": item["content"],
                "agent": item.get("agent") if isinstance(item.get("agent"), str) else None,
                "sources": [
                    source for source in sources if isinstance(source, dict)
                ]
                if isinstance(sources, list)
                else [],
            }
        )
    st.session_state.chat_messages = loaded_messages
    st.session_state.conversation_id = conversation_id
    st.session_state.loaded_conversation_id = conversation_id


st.set_page_config(page_title="Agentic RAG", page_icon="📚", layout="wide")
st.title("Agentic RAG + Web Search")

if "access_token" not in st.session_state:
    st.caption("Sign in to chat with your documents and tools.")
    login_tab, register_tab = st.tabs(["Log in", "Create account"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in", type="primary")
        if submitted:
            try:
                tokens = login(username, password)
                user = get_current_user(tokens["access_token"])
            except (requests.RequestException, KeyError, ValueError) as error:
                st.error(_request_error(error) if isinstance(error, requests.RequestException) else "Login response was invalid.")
            else:
                st.session_state.access_token = tokens["access_token"]
                st.session_state.refresh_token = tokens["refresh_token"]
                st.session_state.current_user = user
                st.session_state.chat_messages = []
                st.session_state.conversation_id = None
                st.rerun()

    with register_tab:
        with st.form("register_form"):
            new_username = st.text_input("Username", key="register_username")
            new_password = st.text_input("Password (at least 12 characters)", type="password")
            confirm_password = st.text_input("Confirm password", type="password")
            register_submitted = st.form_submit_button("Create account")
        if register_submitted:
            if new_password != confirm_password:
                st.error("The passwords do not match.")
            else:
                try:
                    register(new_username, new_password)
                    st.success("Account created. Log in with your new account.")
                except requests.RequestException as error:
                    st.error(_request_error(error))

    st.stop()

access_token = st.session_state.access_token
current_user = st.session_state.current_user
st.session_state.setdefault("chat_messages", [])
st.session_state.setdefault("conversation_id", None)
st.session_state.setdefault("loaded_conversation_id", None)

with st.sidebar:
    st.header("Account")
    st.write(f"**{current_user.get('username', 'User')}**")
    st.caption(f"Role: {current_user.get('role', 'user')}")
    if st.button("Log out", use_container_width=True):
        _clear_authentication()
        st.rerun()

    st.divider()
    st.header("Conversation history")
    if st.button("＋ New chat", use_container_width=True):
        st.session_state.conversation_id = None
        st.session_state.chat_messages = []
        st.session_state.loaded_conversation_id = None
        st.session_state.history_selection = ""

    try:
        conversations = list_conversations(access_token)
        st.session_state.conversations = conversations
    except requests.RequestException as error:
        st.error(_request_error(error))
        conversations = []

    options = {
        item["id"]: f"Chat · {item.get('updated_at', item.get('created_at', ''))[:16]}"
        for item in conversations
        if isinstance(item.get("id"), str)
    }
    conversation_ids = list(options)
    selection_options = [""] + conversation_ids
    current_selection = st.session_state.get("history_selection", "")
    if current_selection not in selection_options:
        current_selection = ""
    selected_id = st.selectbox(
        "Your conversations",
        options=selection_options,
        index=selection_options.index(current_selection),
        format_func=lambda value: "Select a conversation" if not value else options.get(value, value),
        label_visibility="collapsed",
    )
    st.session_state.history_selection = selected_id
    if selected_id and selected_id != st.session_state.loaded_conversation_id:
        try:
            _load_conversation(access_token, selected_id)
        except requests.RequestException as error:
            st.error(_request_error(error))

    st.divider()
    st.header("Service")
    try:
        health = get_health()
        st.success(f"Backend online · {health['service']}")
    except requests.RequestException:
        st.warning("Backend unavailable")

st.caption(
    "The supervisor routes each message to direct chat, your authorized documents, "
    "web search, the calculator, or a bounded combination of agents."
)

for item in st.session_state.chat_messages:
    with st.chat_message(item["role"]):
        st.markdown(item["content"])
        if item["role"] == "assistant":
            st.caption(f"Agent: {item.get('agent') or 'unknown (older message)'}")
            sources = item.get("sources", [])
            with st.expander("Sources"):
                if sources:
                    for source in sources:
                        title = source.get("title") or source.get("source") or "Source"
                        url = source.get("url")
                        if isinstance(url, str) and url.startswith(("http://", "https://")):
                            st.markdown(f"- [{title}]({url})")
                        else:
                            st.markdown(f"- {title}")
                else:
                    st.caption("No sources were returned for this response.")

prompt = st.chat_input("Ask a question")
if prompt:
    st.session_state.chat_messages.append(
        {"role": "user", "content": prompt, "agent": None, "sources": []}
    )
    with st.chat_message("user"):
        st.markdown(prompt)

    response_text = ""
    response_sources: list[dict[str, Any]] = []
    agent_name = "Groq direct response"
    stream_error: str | None = None
    with st.chat_message("assistant"):
        answer_placeholder = st.empty()
        agent_placeholder = st.empty()
        agent_placeholder.caption("Agent: Groq · generating")
        try:
            for event in stream_chat(
                prompt,
                access_token,
                st.session_state.conversation_id,
            ):
                if event["type"] == "token":
                    token = event.get("token")
                    if isinstance(token, str):
                        response_text += token
                        answer_placeholder.markdown(response_text)
                elif event["type"] == "done":
                    conversation_id = event.get("conversation_id")
                    if isinstance(conversation_id, str):
                        st.session_state.conversation_id = conversation_id
                        st.session_state.history_selection = conversation_id
                        st.session_state.loaded_conversation_id = conversation_id
                    name = event.get("agent")
                    if isinstance(name, str):
                        agent_name = name
                    sources = event.get("sources")
                    if isinstance(sources, list):
                        response_sources = [
                            source for source in sources if isinstance(source, dict)
                        ]
                    agent_placeholder.caption(f"Agent: {agent_name}")
                elif event["type"] == "error":
                    stream_error = str(event.get("message", "Chat generation failed."))
        except (requests.RequestException, ValueError) as error:
            stream_error = _request_error(error) if isinstance(error, requests.RequestException) else str(error)

        if response_text and not stream_error:
            with st.expander("Sources"):
                if response_sources:
                    for source in response_sources:
                        title = source.get("title") or source.get("source") or "Source"
                        url = source.get("url")
                        if isinstance(url, str) and url.startswith(("http://", "https://")):
                            st.markdown(f"- [{title}]({url})")
                        else:
                            st.markdown(f"- {title}")
                else:
                    st.caption("No sources were returned for this response.")

    if stream_error:
        st.error(stream_error)
    elif response_text:
        st.session_state.chat_messages.append(
            {
                "role": "assistant",
                "content": response_text,
                "agent": agent_name,
                "sources": response_sources,
            }
        )
        st.rerun()
