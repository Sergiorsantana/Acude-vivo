# Atualiza os dados do Açude Vivo e envia ao GitHub (o site se republica sozinho).
# Roda todo dia pelo Agendador de Tarefas do Windows ("Acude Vivo - atualizar dados").
# Para rodar na mão:  powershell -ExecutionPolicy Bypass -File .\atualizar_e_enviar.ps1

$ErrorActionPreference = "Continue"
$raiz = $PSScriptRoot
$app = Join-Path $raiz "monitor-reservatorios"
$logDir = Join-Path $raiz "logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("atualizacao_{0:yyyy-MM}.log" -f (Get-Date))
$env:PYTHONIOENCODING = "utf-8"

function Registrar($msg) {
    $linha = "[{0:dd/MM/yyyy HH:mm}] {1}" -f (Get-Date), $msg
    Add-Content -Path $log -Value $linha -Encoding utf8
    Write-Output $linha
}

Set-Location $raiz
Registrar "Início"

# 1. traz o que estiver no GitHub (evita conflito no envio)
git pull --rebase --autostash 2>&1 | ForEach-Object { Add-Content $log "  $_" -Encoding utf8 }

# 2. baixa os dados
Set-Location $app
python atualizar_dados.py 2>&1 | ForEach-Object { Add-Content $log "  $_" -Encoding utf8 }
if ($LASTEXITCODE -ne 0) {
    Registrar "ERRO: a coleta falhou (fonte fora do ar?). Nada foi enviado."
    exit 1
}

# 3. redesenha os gráficos do README
python gerar_graficos.py 2>&1 | ForEach-Object { Add-Content $log "  $_" -Encoding utf8 }

# 4. envia ao GitHub
Set-Location $raiz
git add monitor-reservatorios/dados.json monitor-reservatorios/municipios.geojson monitor-reservatorios/transposicao.geojson docs/graficos
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Registrar "Sem mudanças nos dados."
    exit 0
}
git commit -m ("Atualiza dados {0:yyyy-MM-dd}" -f (Get-Date)) 2>&1 | ForEach-Object { Add-Content $log "  $_" -Encoding utf8 }
git push 2>&1 | ForEach-Object { Add-Content $log "  $_" -Encoding utf8 }
if ($LASTEXITCODE -ne 0) {
    Registrar "ERRO: não consegui enviar ao GitHub. Rode 'git push' na pasta para ver o motivo."
    exit 1
}
Registrar "Concluído: dados enviados ao GitHub."
