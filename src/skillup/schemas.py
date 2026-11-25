"""I contratti del servizio: cosa entra, cosa esce, cosa deve restituire il modello."""

from typing import Literal

from pydantic import BaseModel, Field

# --- chat RAG -------------------------------------------------------------------------


class DomandaChat(BaseModel):
    domanda: str = Field(min_length=3, max_length=1000)
    corso_id: str | None = Field(default=None, examples=["02_docker-devops"])


class Fonte(BaseModel):
    pagina: str
    sezione: str
    link: str
    file: str


class RispostaModello(BaseModel):
    """Quello che il modello deve compilare. I link NON li scrive lui: dà i numeri."""

    risposta: str = Field(description="La risposta, in italiano, basata solo sui passaggi")
    fonti_usate: list[int] = Field(description="I numeri [n] dei passaggi usati")
    non_lo_so: bool = Field(description="true se i passaggi non contengono la risposta")


class RispostaChat(BaseModel):
    risposta: str
    fonti: list[Fonte]
    non_lo_so: bool
    recuperati: list[str] = Field(description="i file dei passaggi recuperati, per la misura")
    ms: dict[str, int] = Field(description="millisecondi per passo")


# --- agente piano di studi ---------------------------------------------------------------


class RichiestaPiano(BaseModel):
    obiettivo: str = Field(min_length=5, max_length=500)


class PassoPiano(BaseModel):
    ordine: int
    titolo: str
    link: str = Field(description="il link della pagina, copiato dai risultati degli strumenti")
    perche: str


class PianoProposto(BaseModel):
    obiettivo: str
    passi: list[PassoPiano]
    note: str = ""


class PianoOut(BaseModel):
    id: int
    stato: Literal["proposto", "approvato", "fallito"]
    motivo_fine: str
    piano: PianoProposto | None
    passi_agente: int
    token: int


# --- misura ------------------------------------------------------------------------------


class Giudizio(BaseModel):
    voto: float = Field(ge=0, le=1, description="1 corretta e completa, 0.5 parziale, 0 sbagliata")
    motivo: str