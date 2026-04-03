import argparse
import sys
import readline  # noqa: F401

import httpx

API_BASE_URL = "http://127.0.0.1:8000"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--resume", type=str, default=None, help="候选人简历 markdown 文件路径")
    parser.add_argument("--jd", type=str, default=None, help="职位描述 JD markdown 文件路径")
    parser.add_argument("--api-url", type=str, default=API_BASE_URL, help="后端 API 地址")
    args = parser.parse_args()

    api_url = args.api_url.rstrip("/")

    print("=== Multi-Agent Interview Simulator ===")
    position = input("岗位: ")
    resume = input("简历简述: ")

    candidate_response = f"岗位：{position}。简历：{resume}"

    try:
        resp = httpx.post(
            f"{api_url}/sessions",
            json={
                "max_turns": args.turns,
                "candidate_response": candidate_response,
                "resume_path": args.resume,
                "jd_path": args.jd,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
    except httpx.RequestError as e:
        print(f"[错误] 无法连接后端: {e}")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"[错误] 创建会话失败: {e}")
        sys.exit(1)

    session_data = resp.json()
    session_id = session_data["session_id"]

    while True:
        try:
            resp = httpx.post(
                f"{api_url}/sessions/{session_id}/step",
                json={"candidate_response": candidate_response},
                timeout=120.0,
            )
            resp.raise_for_status()
        except httpx.RequestError as e:
            print(f"[错误] 请求失败: {e}")
            break
        except httpx.HTTPStatusError as e:
            print(f"[错误] 服务端返回错误: {e}")
            break

        result = resp.json()

        if result.get("question"):
            print(f"\n[{result['agent'].upper()}] {result['question']}")

        if result.get("finished"):
            print("\n=== 面试结束 ===")
            if result.get("report"):
                print(f"\n[面评报告]\n{result['report']}")
            break

        user_input = input("你的回答: ")
        candidate_response = user_input

    if not result.get("finished"):
        print("\n=== 面试结束 ===")


if __name__ == "__main__":
    main()
