from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from searcher import search_web
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"]
                   
                   
                   )

class GenerateRequest(BaseModel):
    topic: str          # FastAPI automatically validates 

@app.get('/health')
async def health():
    return {'status': 'ok'}
@app.post('/generate')
async def generate(request: GenerateRequest):
    topic = request.topic   
    return topic          