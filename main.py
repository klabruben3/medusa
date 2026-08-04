from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class NameRequest(BaseModel):
    name: str


@app.get("/")
async def root():
    return {"message": "Hello Ruben, im from the root."}


@app.post("/greet")
def greet(request: NameRequest):
    return {"message": f"Hi {request.name}, im from the /greet endpoint"}
