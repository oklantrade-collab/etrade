import inspect
from app.stocks.decision_engine import DecisionEngine

print("File:", inspect.getfile(DecisionEngine))
print("Signature:", inspect.signature(DecisionEngine.execute_full_analysis))
