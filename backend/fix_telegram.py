with open('c:/Fuentes/eTrade/backend/app/workers/forex_execution_service.py', 'r', encoding='utf-8') as f:
    content = f.read()

target1 = '''        self._close_position(pos, price, result['rule_code'], pnl['pnl_pips'])
        self._send_telegram(
            f"CIERRE PROACTIVO FOREX [{symbol}]\\n"
            f"Regla: {result['rule_code']}\\n"
            f"Pips: +{pnl['pnl_pips']:.1f}\\n"
            f"Razon: {result['reason']}"
        )'''

repl1 = '''        closed = self._close_position(pos, price, result['rule_code'], pnl['pnl_pips'])
        if closed:
            self._send_telegram(
                f"CIERRE PROACTIVO FOREX [{symbol}]\\n"
                f"Regla: {result['rule_code']}\\n"
                f"Pips: +{pnl['pnl_pips']:.1f}\\n"
                f"Razon: {result['reason']}"
            )'''

target2 = '''                    self.log(f"Error actualizando estado anti-loss forex para {symbol}: {upd_e}")
                return'''

repl2 = '''                    self.log(f"Error actualizando estado anti-loss forex para {symbol}: {upd_e}")
                return False'''

target3 = '''            self.log(f'Cerrada {symbol}: {reason} | PnL: {pips_pnl:.1f} pips | USD: {pnl_usd:.2f}')
        except Exception as e: self.log(f'Error cierre: {e}')'''

repl3 = '''            self.log(f'Cerrada {symbol}: {reason} | PnL: {pips_pnl:.1f} pips | USD: {pnl_usd:.2f}')
            return True
        except Exception as e:
            self.log(f'Error cierre: {e}')
            return False'''

content = content.replace(target1, repl1)
content = content.replace(target2, repl2)
content = content.replace(target3, repl3)

with open('c:/Fuentes/eTrade/backend/app/workers/forex_execution_service.py', 'w', encoding='utf-8') as f:
    f.write(content)
