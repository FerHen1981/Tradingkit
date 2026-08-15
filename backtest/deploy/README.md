# Deploy the Backtest Lab cockpit to bck.mex-traders.com

Prereqs (already done): DNS `bck` -> the VPS, and the backtest venv at
`/root/mex-journal/.venv-bt` (numpy/pandas not needed by the cockpit, but the
venv is where `backtest` is importable from).

## 1. Owner secret (off the repo)
```bash
sudo tee /etc/mex-lab.env >/dev/null <<ENV
LAB_PASSWORD=choose-a-strong-password
LAB_SECRET=$(head -c 32 /dev/urandom | base64)
ENV
sudo chmod 600 /etc/mex-lab.env
```

## 2. systemd service
```bash
sudo cp /root/mex-journal/backtest/deploy/mex-lab.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mex-lab
curl -s localhost:8090/healthz    # -> ok
```

## 3. nginx vhost + TLS cert
```bash
sudo cp /root/mex-journal/backtest/deploy/nginx-bck.conf /etc/nginx/sites-available/bck.mex-traders.com
sudo ln -sf /etc/nginx/sites-available/bck.mex-traders.com /etc/nginx/sites-enabled/
sudo certbot --nginx -d bck.mex-traders.com     # issues the cert + wires SSL
sudo nginx -t && sudo systemctl reload nginx
```

## 4. Verify
Open https://bck.mex-traders.com — owner login, then the runs dashboard + the
upload panel. Upload a raw export straight from the browser; it is normalized
and cataloged server-side into `/data/lab/datasets/<name>/`.

Update later: `cd /root/mex-journal && git pull && sudo systemctl restart mex-lab`.
