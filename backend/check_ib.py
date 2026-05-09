from app.data.ib_provider import IBProvider
import asyncio

async def check_ib():
    provider = IBProvider()
    try:
        connected = await provider.connect()
        print(f"IB CONNECTION STATUS: {'CONNECTED' if connected else 'DISCONNECTED'}")
        if connected:
            status = provider.conn.get_status()
            print(f"Status Details: {status}")
    except Exception as e:
        print(f"Error checking IB: {e}")
    finally:
        if provider.conn and provider.conn.connected:
            await provider.disconnect()

if __name__ == "__main__":
    asyncio.run(check_ib())
