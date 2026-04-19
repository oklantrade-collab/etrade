import requests
r = requests.get('http://localhost:8080/api/v1/stocks/universe')
d = r.json()
print(f"Total: {d['total']}")
for u in d['universe'][:10]:
    t = u['ticker']
    p = u['price']
    fs = u['fundamental_score']
    rg = u['revenue_growth']
    gm = u['gross_margin']
    rs = u['rs_score']
    io = u['inst_ownership']
    pt = u['pool_type']
    print(f"  {t}: price=${p}, fund_score={fs}, rev_growth={rg}%, margin={gm}%, rs={rs}, inst={io}%, pool={pt}")
