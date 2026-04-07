import json
import re
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any

######################################
## Arquivo para funções reutilizáveis
######################################

def _validar_cpf_completo(cpf: str) -> bool:
    cpf = re.sub(r'\D', '', cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    resto = (soma * 10) % 11
    if resto == 10:
        resto = 0
    if resto != int(cpf[9]):
        return False

    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    resto = (soma * 10) % 11
    if resto == 10:
        resto = 0
    if resto != int(cpf[10]):
        return False

    return True


def validar_dados(cpf: str, email: str, telefone: str):
    telefone_limpo = re.sub(r'\D', '', telefone)
    cpf_valido = _validar_cpf_completo(cpf)

    padrao_email = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    email_valido = re.match(padrao_email, email) is not None

    telefone_valido = telefone_limpo.isdigit() and len(telefone_limpo) in (10, 11)

    resultado = {
        "cpf": {
            "valor": cpf,
            "status": "válido" if cpf_valido else "inválido"
        },
        "email": {
            "valor": email,
            "status": "válido" if email_valido else "inválido"
        },
        "telefone": {
            "valor": telefone,
            "status": "válido" if telefone_valido else "inválido"
        }
    }
    return resultado

TZ_BR = ZoneInfo("America/Sao_Paulo")

_DOW_PT = {
    "segunda": 0, "segunda-feira": 0,
    "terca": 1, "terça": 1, "terca-feira": 1, "terça-feira": 1,
    "quarta": 2, "quarta-feira": 2,
    "quinta": 3, "quinta-feira": 3,
    "sexta": 4, "sexta-feira": 4,
    "sabado": 5, "sábado": 5, "sabado-feira": 5, "sábado-feira": 5,
    "domingo": 6,
}

_DOW_NAME_PT = {
    0: "segunda-feira",
    1: "terça-feira",
    2: "quarta-feira",
    3: "quinta-feira",
    4: "sexta-feira",
    5: "sábado",
    6: "domingo",
}

def _normalize(s: str) -> str:
    s = s.lower().strip()
    s = s.replace("ç", "c").replace("ã", "a").replace("á", "a").replace("à", "a").replace("â", "a")
    s = s.replace("é", "e").replace("ê", "e")
    s = s.replace("í", "i")
    s = s.replace("ó", "o").replace("ô", "o")
    s = s.replace("ú", "u")
    return s

def _next_weekday(start: date, target_weekday: int) -> date:
    # retorna o próximo target_weekday a partir de start (exclui o próprio dia)
    days_ahead = (target_weekday - start.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return start + timedelta(days=days_ahead)

def _this_or_next_weekday(start: date, target_weekday: int) -> date:
    # permite hoje se bater, senão o próximo
    days_ahead = (target_weekday - start.weekday()) % 7
    return start + timedelta(days=days_ahead)

def resolver_data(texto: str, agora: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Resolve datas relativas/absolutas em pt-BR usando TZ_BR.

    Retorna:
      {
        "ok": bool,
        "data": "DD/MM/AAAA",
        "dia_semana": "quarta-feira",
        "motivo": str | None,
        "entrada_detectada": {...},
        "sugestao": "DD/MM/AAAA" | None
      }
    """
    if agora is None:
        agora = datetime.now(tz=TZ_BR)
    hoje = agora.date()

    raw = texto or ""
    t = _normalize(raw)

    # 1) amanhã / hoje
    if re.search(r"\bamanha\b", t):
        d = hoje + timedelta(days=1)
        return {
            "ok": True,
            "data": d.strftime("%d/%m/%Y"),
            "dia_semana": _DOW_NAME_PT[d.weekday()],
            "motivo": None,
            "entrada_detectada": {"tipo": "relativa", "token": "amanhã"},
            "sugestao": None,
        }
    if re.search(r"\bhoje\b", t):
        d = hoje
        return {
            "ok": True,
            "data": d.strftime("%d/%m/%Y"),
            "dia_semana": _DOW_NAME_PT[d.weekday()],
            "motivo": None,
            "entrada_detectada": {"tipo": "relativa", "token": "hoje"},
            "sugestao": None,
        }

    # 2) "proxima quarta" / "próxima quarta"
    m_next = re.search(r"\bproxim[ao]\s+([a-z\-]+)\b", t)
    if m_next:
        dow_token = m_next.group(1)
        if dow_token in _DOW_PT:
            target = _DOW_PT[dow_token]
            d = _next_weekday(hoje, target)
            return {
                "ok": True,
                "data": d.strftime("%d/%m/%Y"),
                "dia_semana": _DOW_NAME_PT[d.weekday()],
                "motivo": None,
                "entrada_detectada": {"tipo": "relativa", "token": f"próxima {dow_token}"},
                "sugestao": None,
            }

    # 3) dia da semana sozinho ("quarta-feira", "quarta")
    for token, wd in _DOW_PT.items():
        if re.search(rf"\b{re.escape(token)}\b", t):
            d = _next_weekday(hoje, wd)
            return {
                "ok": True,
                "data": d.strftime("%d/%m/%Y"),
                "dia_semana": _DOW_NAME_PT[d.weekday()],
                "motivo": None,
                "entrada_detectada": {"tipo": "dia_semana", "token": token},
                "sugestao": None,
            }

    # 4) datas DD/MM ou DD/MM/AAAA
    m_date = re.search(r"\b(\d{1,2})[\/\-](\d{1,2})(?:[\/\-](\d{2,4}))?\b", t)
    if m_date:
        dd = int(m_date.group(1))
        mm = int(m_date.group(2))
        yy_raw = m_date.group(3)

        if yy_raw:
            yy = int(yy_raw)
            if yy < 100:
                yy += 2000
        else:
            # sem ano: assume ano corrente; se já passou, joga pro próximo ano
            yy = hoje.year

        # valida data
        try:
            d = date(yy, mm, dd)
        except ValueError:
            return {
                "ok": False,
                "data": None,
                "dia_semana": None,
                "motivo": "Data inválida (dia/mês não existe).",
                "entrada_detectada": {"tipo": "data", "token": m_date.group(0)},
                "sugestao": None,
            }

        # se veio sem ano e a data já passou, joga pro próximo ano
        if not yy_raw and d < hoje:
            d = date(hoje.year + 1, mm, dd)

        return {
            "ok": True,
            "data": d.strftime("%d/%m/%Y"),
            "dia_semana": _DOW_NAME_PT[d.weekday()],
            "motivo": None,
            "entrada_detectada": {"tipo": "data", "token": m_date.group(0)},
            "sugestao": None,
        }

    # nada detectado
    return {
        "ok": False,
        "data": None,
        "dia_semana": None,
        "motivo": "Nenhuma data/dia da semana detectado no texto.",
        "entrada_detectada": {"tipo": "nenhum"},
        "sugestao": None,
    }