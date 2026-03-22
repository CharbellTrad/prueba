"""
=============================================================================
  Pasarela de Pagos VE — Cliente Python (REST v2)
  Gateway: MegaSoft Computación C.A.
  Cubre: Tarjeta Crédito/Débito, Pago Móvil C2P/P2C, Vuelto Pago Móvil,
         Crédito Inmediato, Depósito, Zelle, Criptomonedas (vía CryptoBuyer),
         Débito Inmediato, Banplus Pay
=============================================================================
"""
import base64
import logging
import re
import requests
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

@dataclass
class PGConfig:
    """Credenciales y URLs del Payment Gateway."""
    base_url: str
    usuario: str
    contrasena: str
    codafiliacion: str

    @property
    def auth_header(self) -> str:
        credentials = f"{self.usuario}:{self.contrasena}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    @property
    def headers(self) -> dict:
        return {
            "Authorization": self.auth_header,
            "Content-Type": "text/xml",
        }


# ---------------------------------------------------------------------------
# VALIDACIONES DE ENTRADA (según manual MegaSoft v4.27 §4)
# ---------------------------------------------------------------------------

# Prefijos válidos de operadoras VE
_PREFIJOS_VE = ('0412', '0414', '0416', '0424', '0426')

# Formatos de cédula/RIF aceptados por el gateway
_RE_CID = re.compile(r'^[VJEGPCR]\d{5,10}$', re.IGNORECASE)
_RE_TELEFONO = re.compile(r'^04\d{9}$')
_RE_BANCO_VE = re.compile(r'^\d{4}$')
_RE_CODIGO_C2P = re.compile(r'^\d{8}$')
_RE_PAN = re.compile(r'^\d{13,19}$')
_RE_CVV = re.compile(r'^\d{3,4}$')
_RE_EXPDATE = re.compile(r'^\d{4}$')  # MMAA
_RE_CUENTA = re.compile(r'^\d{20}$')
_RE_REFERENCIA = re.compile(r'^[A-Za-z0-9]{1,12}$')
_RE_FACTURA = re.compile(r'^[A-Za-z0-9]{0,20}$')
_RE_OTP = re.compile(r'^\d{1,12}$')
_RE_NUM_DEPOSITO = re.compile(r'^[A-Za-z0-9]{1,20}$')


def validate_cid(value: str, test_mode: bool = False) -> str:
    """Valida y normaliza cédula/RIF.  Formato: [V|J|E|G|P|C|R] + 5-10 dígitos."""
    if not value:
        raise ValueError("La cédula/RIF es requerida.")
    val = value.strip().upper()
    if not test_mode and not _RE_CID.match(val):
        raise ValueError(
            f"Cédula/RIF inválida: '{value}'. "
            "Formato: letra (V/J/E/G/P/C/R) + 5 a 10 dígitos. Ej: V12345678"
        )
    return val


def validate_telefono(value: str, test_mode: bool = False) -> str:
    """Valida teléfono VE: exactamente 11 dígitos empezando por 04XX."""
    if not value:
        raise ValueError("El teléfono es requerido.")
    val = re.sub(r'[\s\-\.\(\)\+]', '', value.strip())
    if not test_mode and not _RE_TELEFONO.match(val):
        raise ValueError(
            f"Teléfono inválido: '{value}'. "
            "Debe ser 11 dígitos empezando por 04. Ej: 04241234567"
        )
    return val


def validate_banco_ve(value: str) -> str:
    """Valida código de banco VE: exactamente 4 dígitos."""
    if not value:
        raise ValueError("El código de banco es requerido.")
    val = value.strip()
    if not _RE_BANCO_VE.match(val):
        raise ValueError(
            f"Código de banco inválido: '{value}'. "
            "Debe ser exactamente 4 dígitos. Ej: 0134"
        )
    return val


def validate_codigo_c2p(value: str) -> str:
    """Valida código C2P: exactamente 8 dígitos."""
    if not value:
        raise ValueError("El código C2P es requerido.")
    val = value.strip()
    if not _RE_CODIGO_C2P.match(val):
        raise ValueError(
            f"Código C2P inválido: '{value}'. "
            "Debe ser exactamente 8 dígitos."
        )
    return val


def validate_pan(value: str) -> str:
    """Valida PAN de tarjeta: 13-19 dígitos."""
    if not value:
        raise ValueError("El número de tarjeta es requerido.")
    val = re.sub(r'[\s\-]', '', value.strip())
    if not _RE_PAN.match(val):
        raise ValueError(
            f"Número de tarjeta inválido. "
            "Debe contener entre 13 y 19 dígitos."
        )
    return val


def validate_cvv(value: str) -> str:
    """Valida CVV/CVC: 3 o 4 dígitos."""
    if not value:
        raise ValueError("El CVV es requerido.")
    val = value.strip()
    if not _RE_CVV.match(val):
        raise ValueError(
            f"CVV inválido: '{value}'. "
            "Debe ser 3 o 4 dígitos."
        )
    return val


def validate_expdate(value: str) -> str:
    """Valida fecha de expiración: MMAA con mes válido (01-12)."""
    if not value:
        raise ValueError("La fecha de vencimiento es requerida.")
    val = re.sub(r'[/\-]', '', value.strip())
    if not _RE_EXPDATE.match(val):
        raise ValueError(
            f"Fecha de vencimiento inválida: '{value}'. "
            "Formato MMAA. Ej: 1226"
        )
    mes = int(val[:2])
    if mes < 1 or mes > 12:
        raise ValueError(f"Mes de vencimiento inválido: {mes:02d}. Debe ser 01-12.")
    return val


def validate_cuenta(value: str) -> str:
    """Valida número de cuenta bancaria: exactamente 20 dígitos."""
    if not value:
        raise ValueError("El número de cuenta es requerido.")
    val = re.sub(r'[\s\-]', '', value.strip())
    if not _RE_CUENTA.match(val):
        raise ValueError(
            f"Número de cuenta inválido: '{value}'. "
            "Debe ser exactamente 20 dígitos."
        )
    return val


def validate_referencia(value: str) -> str:
    """Valida referencia: alfanumérico, hasta 12 caracteres."""
    if not value:
        raise ValueError("La referencia es requerida.")
    val = value.strip()
    if not _RE_REFERENCIA.match(val):
        raise ValueError(
            f"Referencia inválida: '{value}'. "
            "Debe ser alfanumérica, máximo 12 caracteres."
        )
    return val


def validate_otp(value: str) -> str:
    """Valida código OTP: 1-12 dígitos."""
    if not value:
        raise ValueError("El código OTP es requerido.")
    val = value.strip()
    if not _RE_OTP.match(val):
        raise ValueError(
            f"Código OTP inválido: '{value}'. "
            "Debe ser numérico, entre 1 y 12 dígitos."
        )
    return val


def validate_amount(value) -> str:
    """
    Valida y formatea monto: siempre retorna string con 2 decimales.
    Acepta float, int o string.
    """
    try:
        amt = float(str(value).replace(',', '.'))
    except (ValueError, TypeError):
        raise ValueError(f"Monto inválido: '{value}'. Debe ser numérico.")
    if amt <= 0:
        raise ValueError(f"El monto debe ser mayor a cero. Recibido: {amt}")
    return "{:.2f}".format(amt)


def validate_num_deposito(value: str) -> str:
    """Valida número de depósito: alfanumérico, hasta 20 caracteres."""
    if not value:
        raise ValueError("El número de depósito es requerido.")
    val = value.strip()
    if not _RE_NUM_DEPOSITO.match(val):
        raise ValueError(
            f"Número de depósito inválido: '{value}'. "
            "Alfanumérico, máximo 20 caracteres."
        )
    return val


# ---------------------------------------------------------------------------
# UTILIDADES XML
# ---------------------------------------------------------------------------

def parse_xml_response(xml_text: str) -> dict:
    """
    Parsea el XML de respuesta del PG a un dict Python.
    Maneja voucher con tags <linea> y también voucher como texto plano.
    Incluye siempre la clave 'gateway_response_xml' con el XML crudo.
    """
    result = {'gateway_response_xml': xml_text}
    try:
        root = ET.fromstring(xml_text)
        for child in root:
            tag = child.tag.lower()
            if tag == "voucher":
                # Intentar con tags <linea> primero
                lineas = child.findall("linea")
                if lineas:
                    lines = []
                    for line in lineas:
                        text = line.text or ""
                        # Según el manual: los _ deben sustituirse por espacios
                        lines.append(text.replace("_", " "))
                    result[tag] = "\n".join(lines)
                else:
                    # Voucher como texto plano (sin tags <linea>)
                    voucher_text = ET.tostring(child, encoding='unicode', method='text')
                    if voucher_text:
                        result[tag] = voucher_text.strip()
                    else:
                        result[tag] = child.text or ""
            else:
                result[tag] = child.text or ""
        return result
    except ET.ParseError as e:
        _logger.warning("Error parseando XML de respuesta: %s", str(e))
        result["raw"] = xml_text
        return result


def sanitize_factura(value: str) -> str:
    """
    El gateway solo acepta letras y números en el campo factura.
    Refs de Odoo como 'POS/001/0001' se convierten a 'POS0010001'.
    Máximo 20 caracteres.
    """
    return re.sub(r'[^a-zA-Z0-9]', '', str(value))[:20]


def build_xml(tag: str, fields: dict) -> str:
    """Construye XML sanitizando caracteres especiales y omitiendo vacíos."""
    from xml.sax.saxutils import escape
    inner = ""
    for k, v in fields.items():
        if v is not None and v != "":   # Filtrar None Y strings vacíos
            val = sanitize_factura(v) if k == "factura" else str(v)
            inner += f"<{k}>{escape(val)}</{k}>"
    return f"<{tag}>{inner}</{tag}>"


# ---------------------------------------------------------------------------
# CLIENTE BASE
# ---------------------------------------------------------------------------

class PaymentGatewayClient:
    """Cliente para la Pasarela de Pagos Bancaria VE (REST v2)."""

    def __init__(self, config: PGConfig, timeout: int = 30, test_mode: bool = False):
        self.config = config
        self.timeout = timeout
        self.test_mode = test_mode

    def _post(self, endpoint: str, body: str) -> dict:
        url = f"{self.config.base_url}{endpoint}"
        try:
            _logger.info("PG Request → %s", url)
            _logger.debug("PG Body: %s", body)
            resp = requests.post(
                url,
                data=body.encode("utf-8"),
                headers=self.config.headers,
                timeout=self.timeout,
                verify=True,
            )
            resp.raise_for_status()
            _logger.debug("PG Response: %s", resp.text)
            return parse_xml_response(resp.text)
        except requests.exceptions.Timeout:
            return {"error": "Timeout al conectar con la Pasarela de Pagos"}
        except requests.exceptions.SSLError as e:
            return {"error": f"Error SSL: {str(e)}"}
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    # -----------------------------------------------------------------------
    # 1. PRE-REGISTRO (obligatorio antes de cualquier transacción)
    # -----------------------------------------------------------------------
    def preregistro(self) -> dict:
        """
        Genera un número de control. DEBE llamarse antes de cualquier transacción.
        Returns: dict con 'control' (19 dígitos) y 'codigo' (00=OK)
        """
        body = build_xml("request", {"cod_afiliacion": self.config.codafiliacion})
        return self._post("/payment/action/v2-preregistro", body)

    # -----------------------------------------------------------------------
    # 2. QUERY STATUS
    # -----------------------------------------------------------------------
    def query_status(self, control: str, tipotrx: str, version: int = 3) -> dict:
        """
        Consulta el estado de una transacción.
        tipotrx: CREDITO, C2P, P2C, ZELLE, CRYPTO, CRYPTO_CONFIR,
                 BANPLUSP, BANPLUSP_CONFIR, CREDITO_INMEDIATO,
                 DEBITO_INM, DEBITO_INM_CONFIR, DEPOSITO, ANULACION,
                 C@MBIO_PAGOMOVIL, C@MBIO_PRIVADO
        version: 1 (DEPRECATED), 2, 3 (incluye datos multimoneda)
        """
        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "version": version,
            "tipotrx": tipotrx,
        })
        return self._post("/payment/action/v2-querystatus", body)

    # -----------------------------------------------------------------------
    # 3. COMPRA TARJETA DE CRÉDITO / DÉBITO
    # -----------------------------------------------------------------------
    def compra_tarjeta(
        self,
        control: str,
        pan: str,
        cvv2: str,
        expdate: str,
        amount,
        cid: str,
        client: str,
        factura: Optional[str] = None,
        mode: int = 4,
        tipoPago: str = "10",
        plan: str = "00",
        terminal: Optional[str] = None,
    ) -> dict:
        """
        Procesa un pago con tarjeta de crédito o débito.
        Valida: pan, cvv2, expdate, cid, amount
        tipoPago: '10'=Bs, '40'=USD, '90'=EUR
        mode:     4=Internet (default), 2=Manual Online
        """
        # Validaciones
        pan = validate_pan(pan)
        cvv2 = validate_cvv(cvv2)
        expdate = validate_expdate(expdate)
        amount = validate_amount(amount)
        cid = validate_cid(cid, test_mode=self.test_mode)

        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "transcode": "0141",
            "pan": pan,
            "cvv2": cvv2,
            "cid": cid,
            "expdate": expdate,
            "amount": amount,
            "client": client or "",
            "factura": factura,
            "mode": mode,
            "tipoPago": tipoPago,
            "plan": plan,
            "terminal": terminal,
        })
        return self._post("/payment/action/v2-procesar-compra", body)

    # -----------------------------------------------------------------------
    # 4. PAGO MÓVIL C2P (Comercio a Persona)
    # -----------------------------------------------------------------------
    def pago_movil_c2p(
        self,
        control: str,
        cid: str,
        telefono: str,
        codigobanco: str,
        codigoc2p: str,
        amount,
        factura: Optional[str] = None,
    ) -> dict:
        """
        Verifica un pago recibido por Pago Móvil C2P.
        C2P siempre opera en BOLÍVARES (no tiene parámetro tipoPago).
        """
        # Validaciones
        cid = validate_cid(cid, test_mode=self.test_mode)
        telefono = validate_telefono(telefono, test_mode=self.test_mode)
        codigobanco = validate_banco_ve(codigobanco)
        codigoc2p = validate_codigo_c2p(codigoc2p)
        amount = validate_amount(amount)

        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "cid": cid,
            "telefono": telefono,
            "codigobanco": codigobanco,
            "codigoc2p": codigoc2p,
            "amount": amount,
            "factura": factura,
        })
        return self._post("/payment/action/v2-procesar-compra-c2p", body)

    # -----------------------------------------------------------------------
    # 5. PAGO MÓVIL P2C (Persona a Comercio)
    # -----------------------------------------------------------------------
    def pago_movil_p2c(
        self,
        control: str,
        cid: str,
        telefonoCliente: str,
        codigobancoCliente: str,
        telefonoComercio: str,
        codigobancoComercio: str,
        amount,
        tipoPago: str = "10",
        factura: Optional[str] = None,
    ) -> dict:
        """
        Verifica un pago recibido por Pago Móvil P2C.
        tipoPago: '10'=Bs, '40'=USD, '90'=EUR
        """
        # Validaciones
        if cid:  # Cédula es opcional en P2C según manual
            cid = validate_cid(cid, test_mode=self.test_mode)
        telefonoCliente = validate_telefono(telefonoCliente, test_mode=self.test_mode)
        codigobancoCliente = validate_banco_ve(codigobancoCliente)
        telefonoComercio = validate_telefono(telefonoComercio, test_mode=self.test_mode)
        codigobancoComercio = validate_banco_ve(codigobancoComercio)
        amount = validate_amount(amount)

        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "cid": cid,
            "telefonoCliente": telefonoCliente,
            "codigobancoCliente": codigobancoCliente,
            "telefonoComercio": telefonoComercio,
            "codigobancoComercio": codigobancoComercio,
            "tipoPago": tipoPago,
            "amount": amount,
            "factura": factura,
        })
        return self._post("/payment/action/v2-procesar-compra-p2c", body)

    # -----------------------------------------------------------------------
    # 6. VUELTO POR PAGO MÓVIL (C@mbio Pago Móvil)
    # -----------------------------------------------------------------------
    def vuelto_pago_movil(
        self,
        control: str,
        cid: str,
        telefono: str,
        codigobanco: str,
        amount,
        tipomoneda: str = "0",
        factura: Optional[str] = None,
    ) -> dict:
        """
        Realiza una devolución/vuelto al cliente por Pago Móvil.
        tipomoneda: '0'=Bs (único soportado para vuelto pago móvil)
        """
        # Validaciones
        cid = validate_cid(cid, test_mode=self.test_mode)
        telefono = validate_telefono(telefono, test_mode=self.test_mode)
        codigobanco = validate_banco_ve(codigobanco)
        amount = validate_amount(amount)

        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "cid": cid,
            "telefono": telefono,
            "codigobanco": codigobanco,
            "tipo_moneda": tipomoneda,
            "amount": amount,
            "factura": factura,
        })
        return self._post("/payment/action/v2-procesar-cambio-pagomovil", body)

    # -----------------------------------------------------------------------
    # 7. CRÉDITO INMEDIATO (Verificación de Transferencia)
    # -----------------------------------------------------------------------
    def credito_inmediato(
        self,
        control: str,
        cid: str,
        cuentaOrigen: str,
        telefonoOrigen: str,
        codigobancoOrigen: str,
        cuentaDestino: str,
        amount,
        referencia: Optional[str] = None,
        factura: Optional[str] = None,
    ) -> dict:
        """
        Verifica una transferencia bancaria recibida (crédito inmediato).
        """
        # Validaciones
        cid = validate_cid(cid, test_mode=self.test_mode)
        cuentaOrigen = validate_cuenta(cuentaOrigen)
        telefonoOrigen = validate_telefono(telefonoOrigen, test_mode=self.test_mode)
        codigobancoOrigen = validate_banco_ve(codigobancoOrigen)
        cuentaDestino = validate_cuenta(cuentaDestino)
        amount = validate_amount(amount)
        if referencia:
            referencia = validate_referencia(referencia)

        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "cid": cid,
            "cuentaOrigen": cuentaOrigen,
            "telefonoOrigen": telefonoOrigen,
            "codigobancoOrigen": codigobancoOrigen,
            "cuentaDestino": cuentaDestino,
            "amount": amount,
            "referencia": referencia,
            "factura": factura,
        })
        return self._post("/payment/action/v2-procesar-compra-creditoinmediato", body)

    # -----------------------------------------------------------------------
    # 8. DEPÓSITO
    # -----------------------------------------------------------------------
    def deposito(
        self,
        control: str,
        cid: str,
        numDeposito: str,
        cuentaDestino: str,
        amount,
        factura: Optional[str] = None,
    ) -> dict:
        """Verifica un depósito bancario recibido."""
        # Validaciones
        cid = validate_cid(cid, test_mode=self.test_mode)
        numDeposito = validate_num_deposito(numDeposito)
        cuentaDestino = validate_cuenta(cuentaDestino)
        amount = validate_amount(amount)

        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "cid": cid,
            "numDeposito": numDeposito,
            "cuentaDestino": cuentaDestino,
            "amount": amount,
            "factura": factura,
        })
        return self._post("/payment/action/v2-procesar-compra-deposito", body)

    # -----------------------------------------------------------------------
    # 9. ZELLE
    # -----------------------------------------------------------------------
    def zelle(
        self,
        control: str,
        cid: str,
        codigobancoComercio: str,
        referencia: str,
        amount,
        tipoPago: str = "40",
        client: Optional[str] = None,
        email: Optional[str] = None,
        factura: Optional[str] = None,
    ) -> dict:
        """
        Verifica un pago recibido vía Zelle.
        tipoPago SIEMPRE es '40' (USD) — Zelle es exclusivamente en dólares.
        """
        # Validaciones
        cid = validate_cid(cid, test_mode=self.test_mode)
        referencia = validate_referencia(referencia)
        amount = validate_amount(amount)
        # codigobancoComercio para Zelle no es código numérico VE, es BOFA/CHAS/etc
        if not codigobancoComercio or not codigobancoComercio.strip():
            raise ValueError("El banco Zelle del comercio es requerido.")

        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "cid": cid,
            "codigobancoComercio": codigobancoComercio.strip(),
            "referencia": referencia,
            "amount": amount,
            "factura": factura,
        })
        return self._post("/payment/action/v2-procesar-compra-zelle", body)

    # -----------------------------------------------------------------------
    # 10. CRIPTOMONEDAS — Listar monedas
    # -----------------------------------------------------------------------
    def crypto_get_monedas(self) -> dict:
        """Obtiene la lista de criptomonedas disponibles en CryptoBuyer."""
        body = build_xml("request", {"cod_afiliacion": self.config.codafiliacion})
        return self._post("/payment/action/v2-procesar-crypto-get", body)

    # -----------------------------------------------------------------------
    # 11. CRIPTOMONEDAS — Solicitud (genera QR)
    # -----------------------------------------------------------------------
    def crypto_solicitud(
        self,
        control: str,
        amount,
        tipomoneda: str,
        factura: Optional[str] = None,
    ) -> dict:
        """
        Inicia pago con cripto. Genera QR para mostrar al cliente.
        El amount es en FIAT (USD).
        tipomoneda: 'BNB', 'BTC', 'ETH', 'USDT', 'LTC', 'DASH', 'DAI', 'TRXUSDT'
        Returns: 'monto_crypto', 'qrurl', 'referencia', 'nombre_moneda'
        """
        amount = validate_amount(amount)
        if not tipomoneda or not tipomoneda.strip():
            raise ValueError("Seleccione una criptomoneda.")

        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "amount": amount,
            "tipo_moneda": tipomoneda.strip(),
            "factura": factura,
        })
        return self._post("/payment/action/v2-procesar-crypto-auth", body)

    # -----------------------------------------------------------------------
    # 12. CRIPTOMONEDAS — Confirmación
    # -----------------------------------------------------------------------
    def crypto_confirmacion(self, control: str) -> dict:
        """
        Confirma que el cliente realizó el pago en cripto.
        codigo 'ME' = aún no pagado (reintentar)
        codigo 'MF' = pago inferior
        codigo '00' = APROBADO
        """
        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
        })
        return self._post("/payment/action/v2-procesar-crypto-confir", body)

    # -----------------------------------------------------------------------
    # 13. DÉBITO INMEDIATO — Solicitud
    # -----------------------------------------------------------------------
    def debito_inmediato_solicitud(
        self,
        control: str,
        cid: str,
        telefonoCliente: str,
        codigobancoCliente: str,
        cuentaCliente: str,
        amount,
        factura: Optional[str] = None,
    ) -> dict:
        """
        Solicitud de débito inmediato. Se genera un OTP que el cliente recibe.
        Débito inmediato siempre opera en BOLÍVARES.
        """
        # Validaciones
        cid = validate_cid(cid, test_mode=self.test_mode)
        telefonoCliente = validate_telefono(telefonoCliente, test_mode=self.test_mode)
        codigobancoCliente = validate_banco_ve(codigobancoCliente)
        cuentaCliente = validate_cuenta(cuentaCliente)
        amount = validate_amount(amount)

        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "cid": cid,
            "codigobancoCliente": codigobancoCliente,
            "cuentaCliente": cuentaCliente,
            "telefonoCliente": telefonoCliente,
            "amount": amount,
            "factura": factura,
        })
        return self._post("/payment/action/v2-procesar-debitoinmediato-auth", body)

    # -----------------------------------------------------------------------
    # 14. DÉBITO INMEDIATO — Confirmación
    # -----------------------------------------------------------------------
    def debito_inmediato_confirmacion(
        self,
        control: str,
        cod_otp: str,
    ) -> dict:
        """
        Confirma un débito inmediato con el código OTP del banco.
        """
        cod_otp = validate_otp(cod_otp)

        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "cod_otp": cod_otp,
        })
        return self._post("/payment/action/v2-procesar-debitoinmediato-confir", body)

    # -----------------------------------------------------------------------
    # 15. BANPLUS PAY — Solicitud
    # -----------------------------------------------------------------------
    def banplus_pay_solicitud(
        self,
        control: str,
        cid: str,
        amount,
        tipo_moneda: str = "840",
        tipo_cuenta: str = "720",
        factura: Optional[str] = None,
    ) -> dict:
        """
        Solicitud de pago Banplus Pay.
        tipo_moneda: '0'=Bs, '840'=Dólares, '978'=Euros
        tipo_cuenta: '900'=Bs, '720'=Dólar, '700'=Euro, etc.
        """
        # Validaciones
        cid = validate_cid(cid, test_mode=self.test_mode)
        amount = validate_amount(amount)

        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "cid": cid,
            "monto": amount,
            "tipo_moneda": tipo_moneda,
            "tipo_cuenta": tipo_cuenta,
            "factura": factura,
        })
        return self._post("/payment/action/v2-procesar-banplusp-auth", body)

    # -----------------------------------------------------------------------
    # 16. BANPLUS PAY — Confirmación
    # -----------------------------------------------------------------------
    def banplus_pay_confirmacion(
        self,
        control: str,
        cod_otp: str,
    ) -> dict:
        """Confirma un pago Banplus Pay con el código OTP."""
        cod_otp = validate_otp(cod_otp)

        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "cod_otp": cod_otp,
        })
        return self._post("/payment/action/v2-procesar-banplusp-confir", body)

    # -----------------------------------------------------------------------
    # 17. CIERRE DE LOTE
    # -----------------------------------------------------------------------
    def cierre(self) -> dict:
        """Realiza el cierre del lote de transacciones."""
        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
        })
        return self._post("/payment/action/v2-procesar-cierre", body)

    # -----------------------------------------------------------------------
    # 18. ANULACIÓN
    # -----------------------------------------------------------------------
    def anulacion(
        self,
        control: str,
        terminal: str,
        seqnum: str,
        monto: str,
        factura: str,
        referencia: str,
        ult: str,
        authid: str,
    ) -> dict:
        """
        Reversa una transacción previamente procesada.
        terminal: terminal de la transacción original
        seqnum: número de secuencia de la transacción original
        monto: monto de la transacción original
        referencia: referencia de la transacción original
        ult: últimos 4 dígitos de la tarjeta
        authid: código de autorización de la transacción original
        """
        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "terminal": terminal,
            "seqnum": seqnum,
            "monto": monto,
            "factura": factura,
            "referencia": referencia,
            "ult": ult,
            "authid": authid,
        })
        return self._post("/payment/action/v2-procesar-anulacion", body)


# ---------------------------------------------------------------------------
# CÓDIGOS DE RESPUESTA (según manual MegaSoft v4.27)
# ---------------------------------------------------------------------------

CODIGOS_RESPUESTA = {
    "00": "APROBADA",
    "01": "Solicitar autorización",
    "03": "Comercio no válido",
    "04": "Retener tarjeta",
    "05": "No autorizada",
    "09": "Transacción pendiente",
    "12": "Transacción inválida",
    "13": "Monto inválido",
    "14": "Tarjeta inválida",
    "30": "Error de formato",
    "39": "No es cuenta de crédito",
    "41": "Tarjeta perdida",
    "43": "Tarjeta robada",
    "51": "Fondos insuficientes",
    "54": "Tarjeta vencida",
    "55": "PIN incorrecto",
    "58": "Terminal no autorizado",
    "61": "Monto excede el límite",
    "65": "Intentos de PIN excedidos",
    "75": "Intentos de PIN excedidos",
    "88": "Terminal inválido",
    "91": "Plataforma emisor no disponible",
    "96": "Error del sistema",
    "99": "Error / Control no encontrado",
    "XD": "Terminal o Payment no disponible",
    "YQ": "Requiere autenticación 3D Secure",
    "T2": "Fallo autenticación 3D Secure",
    "T4": "Fallo procesamiento 3D Secure",
    "PC": "Referencia utilizada en otra compra",
    "GA": "Parámetros de entrada errados / No se recibió cédula o RIF",
    "MF": "Pago por monto inferior (cripto)",
    "ME": "Transacción cripto no ha sido pagada",
    "AI": "Plataforma CryptoBuyer no disponible",
    "MK": "No existe la preautorización correspondiente",
    "OO": "Cierre aprobado",
    "Y9": "Monto máximo de lote alcanzado",
    "ZZ": "Servicio no existe",
}


def interpretar_respuesta(response: dict) -> tuple:
    """
    Interpreta la respuesta del gateway.
    Returns: (aprobado: bool, mensaje: str)
    """
    codigo = response.get("codigo", "??")
    descripcion = response.get("descripcion", "Sin descripción")
    aprobado = codigo == "00"
    estado = CODIGOS_RESPUESTA.get(codigo, f"Código: {codigo}")
    mensaje = f"{estado}: {descripcion}" if descripcion else estado
    return aprobado, mensaje
