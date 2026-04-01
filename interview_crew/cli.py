import argparse
from interview_crew.graph import graph
from interview_crew.state import InterviewState


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--turns", type=int, default=6)
    args = parser.parse_args()

    print("=== Multi-Agent Interview Simulator ===")
    position = input("岗位: ")
    resume = input("简历简述: ")

    state: InterviewState = {
        "session_id": "demo-001",
        "turn": 0,
        "max_turns": args.turns,
        "candidate_response": f"岗位：{position}。简历：{resume}",
        "tech_history": [],
        "behavior_history": [],
        "project_history": [],
        "unified_history": [],
        "current_agent": "",
        "last_question": "",
        "status": "ongoing",
    }

    while state["status"] != "finished" and state["turn"] < state["max_turns"]:
        for event in graph.stream(state, config={"recursion_limit": 50}):
            node_name, output = next(iter(event.items()))
            state.update(output)
            if state.get("last_question"):
                print(f"\n[{state['current_agent'].upper()}] {state['last_question']}")
                break
        if state["status"] == "finished" or state["turn"] >= state["max_turns"]:
            break
        user_input = input("你的回答: ")
        state["candidate_response"] = user_input

    print("\n=== 面试结束 ===")


if __name__ == "__main__":
    main()
