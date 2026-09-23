from dotenv import load_dotenv
load_dotenv()

from typesafe_sdk import TypeSafeClient, Noul, Choice

with TypeSafeClient() as client:
    # Confirm API works
    r = client.system_one(
        state="The quick brown fox jumps over the lazy dog.",
        questions={
            "is_english": Noul(instructions="Is this English text?"),
            "topic": Choice(
                instructions="What is this text about?",
                criteria={"animals": None, "weather": None, "other": None},
            ),
        },
    )
    print("noul   :", r.nouls["is_english"].noul)
    print("choice :", r.choices["topic"].choice)
    print("conf   :", r.choices["topic"].confidence)
    print("probs  :", r.choices["topic"].probabilities)