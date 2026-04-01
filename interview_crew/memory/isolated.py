from typing import List
from interview_crew.state import Message


def build_agent_messages(private_history: List[Message], system_prompt: str, candidate_response: str) -> List[Message]:
    messages: List[Message] = [{"role": "system", "content": system_prompt}]
    messages.extend(private_history)
    if candidate_response:
        messages.append({"role": "user", "content": candidate_response})
    return messages
