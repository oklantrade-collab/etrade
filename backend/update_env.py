import subprocess

cmd = [
    "ssh", "-i", "C:/Users/jyups/.ssh/etrade_cloud_key",
    "root@207.154.224.71",
    "python3 -c \"import re; f='/home/etrade/etrade/backend/.env'; c=open(f).read(); open(f,'w').write(re.sub(r'CTRADER_ACCESS_TOKEN=.*', 'CTRADER_ACCESS_TOKEN=sn3EbgYQgSNwr5yK5NeDP09qpyT6eewax07bnDWCHE8', c))\" && systemctl restart etrade-forex"
]

subprocess.run(cmd, check=True)
print("Done!")
