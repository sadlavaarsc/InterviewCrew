from typing import List
from interview_crew.state import Message


def build_agent_messages(
    private_history: List[Message],
    system_prompt: str,
    candidate_response: str,
    business_context: str = "",
    resume_context: str = "",
) -> List[Message]:
    messages: List[Message] = [{"role": "system", "content": system_prompt}]
    if business_context:
        messages.append(
            {
                "role": "system",
                "content": f"【业务背景】\n{business_context}",
            }
        )
    if resume_context:
        messages.append(
            {
                "role": "system",
                "content": f"【候选人简历】\n{resume_context}",
            }
        )
    messages.extend(private_history)
    if candidate_response:
        messages.append({"role": "user", "content": candidate_response})
    return messages
