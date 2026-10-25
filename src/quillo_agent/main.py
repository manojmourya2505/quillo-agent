"""Simple terminal chat for trying the agent. Type 'exit' to quit."""

from quillo_agent.agent import QuilloAgent

MAX_HISTORY_MESSAGES = 10


def main() -> None:
    agent = QuilloAgent()
    history: list[dict] = []
    print("Quillo agent. Ask about your balance, cards, goals, bills or transactions.")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            break

        answer = agent.ask(question, history)
        print(f"Quillo: {answer}\n")
        history += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
        history = history[-MAX_HISTORY_MESSAGES:]


if __name__ == "__main__":
    main()
