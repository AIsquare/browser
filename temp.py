from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI()

models = client.models.list()

for model in sorted(models.data, key=lambda x: x.id):
    print(model.id)