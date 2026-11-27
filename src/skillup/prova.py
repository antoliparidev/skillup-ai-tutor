import asyncio

from skillup.db import Sessione
from skillup.rag import rispondi

async def main() -> None:
    async with Sessione() as s:
        d = "di cosa parla il corso?"
        r = await rispondi(s, d)
        print("Domanda->" + d)
        print("risposta->" + r.risposta)
        print(f"fonti->{r.fonti}")
        print("ms->", r.ms)

asyncio.run(main())