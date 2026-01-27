```uvicorn service.app:app --host 0.0.0.0 --port 8080```

```http://127.0.0.1:8080/docs```

```curl http://localhost:8080/health```

``` curl -i -X POST "http://localhost:8080/lpips"   -H "Content-Type: application/json"   -d '{"ref_path":"/mnt/c/repos/ai_corner/test/ref.png","test_path":"/mnt/c/repos/ai_corner/test/test.png","net":"vgg"}'```