import argparse
import readline  # noqa: F401
from interview_crew.state import InterviewState
from interview_crew.orchestrator.engine import Orchestrator, StepResult


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--resume", type=str, default=None, help="候选人简历 markdown 文件路径")
    parser.add_argument("--jd", type=str, default=None, help="职位描述 JD markdown 文件路径")
    args = parser.parse_args()

    print("=== Multi-Agent Interview Simulator ===")
    position = input("岗位: ")
    resume = input("简历简述: ")

    state = InterviewState(
        session_id="demo-001",
        turn=0,
        max_turns=args.turns,
        candidate_response=f"岗位：{position}。简历：{resume}",
        resume_path=args.resume,
        jd_path=args.jd,
    )

    orchestrator = Orchestrator(state)

    while state.status != "finished" and state.turn < state.max_turns:
        result = orchestrator.step(state.candidate_response)

        if result.question:
            print(f"\n[{result.agent.upper()}] {result.question}")

        if result.finished:
            print("\n=== 面试结束 ===")
            if result.report:
                print(f"\n[面评报告]\n{result.report}")
            break

        user_input = input("你的回答: ")
        state.candidate_response = user_input

    if not result.finished:
        print("\n=== 面试结束 ===")


if __name__ == "__main__":
    main()
