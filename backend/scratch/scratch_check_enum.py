from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOATrendbarPeriod

TF_MAP = {
    '5m':  ProtoOATrendbarPeriod.M5,
    '15m': ProtoOATrendbarPeriod.M15,
    '1h':  ProtoOATrendbarPeriod.H1,
    '4h':  ProtoOATrendbarPeriod.H4,
    '1d':  ProtoOATrendbarPeriod.D1,
}

p_rev = {v: k for k, v in TF_MAP.items()}

print("TF_MAP values:", {k: (v, type(v)) for k, v in TF_MAP.items()})
print("p_rev keys:", {k: type(k) for k in p_rev.keys()})

# Test lookups with standard values
print("p_rev.get(5) ->", p_rev.get(5))
print("p_rev.get(ProtoOATrendbarPeriod.M5) ->", p_rev.get(ProtoOATrendbarPeriod.M5))

# Test with what might be returned by Protobuf
# Some compiled Protobuf versions might use enum wrappers
print("Comparing ProtoOATrendbarPeriod.M5 == 5 ->", ProtoOATrendbarPeriod.M5 == 5)
