```uvicorn app.main:app --host 0.0.0.0 --port 8080```
```uvicorn app.main:app --host 0.0.0.0 --port 8080 --log-level debug```

```http://127.0.0.1:8080/docs```

```curl http://localhost:8080/health```

``` curl -i -X POST "http://localhost:8080/compare"   -H "Content-Type: application/json"   -d '{"ref_path":"/mnt/c/repos/ai_corner/test/ref.png","test_path":"/mnt/c/repos/ai_corner/test/test.png","net":"vgg"}'```
```curl -s -X POST "http://localhost:8080/compare/heatmap"   -H "Content-Type: application/json"   -d '{"metric":"lpips","ref_path":"/mnt/c/repos/ai_corner/test/ref.png","test_path":"/mnt/c/repos/ai_corner/test/test.png","net":"vgg","overlay_on":"test","alpha":0.45}'   --output lpips_heatmap.png```


curl -X 'POST' \
  'http://192.168.2.111:8080/compare/heatmap' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "metric": "lpips",
  "ref_path": "/home/yautay/repos/ai_corner/test/ref_2.png",
  "test_path": "/home/yautay/repos/ai_corner/test/test_2.png",
  "net": "vgg",
  "overlay_on": "test",
  "alpha": 0.45
}'