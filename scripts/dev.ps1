Copy-Item .env.example .env -ErrorAction SilentlyContinue
docker compose up -d --build
Write-Host "VeriSonar en http://localhost:3000  API http://localhost:8000/docs"
