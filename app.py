from ivy_gpt.main import app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "ivy_gpt.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True
    )
