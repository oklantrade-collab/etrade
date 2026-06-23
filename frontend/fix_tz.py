import glob
files = [
    'c:/Fuentes/eTrade/frontend/app/forex/dashboard/page.tsx',
    'c:/Fuentes/eTrade/frontend/app/stocks/dashboard/page.tsx',
    'c:/Fuentes/eTrade/frontend/app/stocks/opportunities/page.tsx',
    'c:/Fuentes/eTrade/frontend/app/stocks/positions/page.tsx',
    'c:/Fuentes/eTrade/frontend/app/forex/positions/page.tsx',
]
for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    if '"timezone": "America/Lima"' in content:
        tvtz = 'const tvTimezone = typeof window !== "undefined" ? (localStorage.getItem("app_timezone") || "America/Lima") : "America/Lima";\n\n        new (window as any).TradingView.widget({'
        content = content.replace('new (window as any).TradingView.widget({', tvtz)
        content = content.replace('"timezone": "America/Lima"', '"timezone": tvTimezone')
        with open(f, 'w', encoding='utf-8') as file:
            file.write(content)
        print(f'Updated {f}')
