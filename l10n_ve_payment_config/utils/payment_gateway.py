"""
=============================================================================
  Pasarela de Pagos VE — Cliente Python (REST v2)
  Gateway: MegaSoft Computación C.A.
  Cubre: Tarjeta Crédito/Débito, Pago Móvil C2P/P2C, Vuelto Pago Móvil,
         Crédito Inmediato, Depósito, Zelle, Criptomonedas (vía CryptoBuyer)
=============================================================================
"""
import base64
import requests
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional


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
# UTILIDADES XML
# ---------------------------------------------------------------------------

def parse_xml_response(xml_text: str) -> dict:
    """Parsea el XML de respuesta del PG a un dict Python."""
    try:
        root = ET.fromstring(xml_text)
        result = {}
        for child in root:
            tag = child.tag.lower()
            if tag == "voucher":
                lines = [line.text or "" for line in child.findall("linea")]
                result[tag] = "\n".join(lines)
            else:
                result[tag] = child.text or ""
        return result
    except ET.ParseError:
        return {"raw": xml_text}


def build_xml(tag: str, fields: dict) -> str:
    """Construye un XML request simple."""
    inner = "".join(f"<{k}>{v}</{k}>" for k, v in fields.items() if v is not None)
    return f"<{tag}>{inner}</{tag}>"


# ---------------------------------------------------------------------------
# CLIENTE BASE
# ---------------------------------------------------------------------------

class PaymentGatewayClient:
    """Cliente para la Pasarela de Pagos Bancaria VE (REST v2)."""

    def __init__(self, config: PGConfig, timeout: int = 30):
        self.config = config
        self.timeout = timeout

    def _post(self, endpoint: str, body: str) -> dict:
        url = f"{self.config.base_url}{endpoint}"
        try:
            resp = requests.post(
                url,
                data=body.encode("utf-8"),
                headers=self.config.headers,
                timeout=self.timeout,
                verify=True,
            )
            resp.raise_for_status()
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
        tipotrx: CREDITO, DEBITO, C2P, P2C, ZELLE, CMBIOPAGOMOVIL,
                 CREDITOINMEDIATO, DEPOSITO, CRYPTOCONFIR, etc.
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
        amount: str,
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
        pan:     Número de tarjeta (hasta 19 dígitos)
        cvv2:    Código de seguridad ('000' si no aplica)
        expdate: MMAA (Ej: '1226')
        amount:  Decimal (Ej: '150.00')
        cid:     Cédula con prefijo (Ej: 'V12345678') — prefijos: V/J/E/G/P/C/R
        tipoPago: '10'=Bs, '40'=USD, '90'=EUR
        plan:    '00'=rotativo, '02'=3 meses, '04'-'35'=cuotas fijas, '40'=meses gracia
        mode:    4=Internet (default), 2=Manual Online
        """
        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "pan": pan,
            "cvv2": cvv2,
            "cid": cid,
            "expdate": expdate,
            "amount": amount,
            "client": client,
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
        amount: str,
        factura: Optional[str] = None,
    ) -> dict:
        """
        Verifica un pago recibido por Pago Móvil C2P.
        codigobanco: código de 4 dígitos del banco del cliente (ej: '0134'=Banesco)
        codigoc2p:   Clave C2P de 8 dígitos del banco
        """
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
        telefonoCliente: str,
        codigobancoCliente: str,
        telefonoComercio: str,
        codigobancoComercio: str,
        amount: str,
        tipoPago: str = "10",
        factura: Optional[str] = None,
    ) -> dict:
        """
        Verifica un pago recibido por Pago Móvil P2C.
        tipoPago: '10'=Bs, '40'=USD, '90'=EUR
        """
        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
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
    # 6. VUELTO POR PAGO MÓVIL
    # -----------------------------------------------------------------------
    def vuelto_pago_movil(
        self,
        control: str,
        cid: str,
        telefono: str,
        codigobanco: str,
        amount: str,
        tipomoneda: str = "0",
        factura: Optional[str] = None,
    ) -> dict:
        """
        Realiza una devolución/vuelto al cliente por Pago Móvil.
        tipomoneda: '0'=Bs, '840'=USD, '978'=EUR
        """
        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "cid": cid,
            "telefono": telefono,
            "codigobanco": codigobanco,
            "tipomoneda": tipomoneda,
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
        amount: str,
        referencia: Optional[str] = None,
        factura: Optional[str] = None,
    ) -> dict:
        """
        Verifica una transferencia bancaria recibida.
        cuentaOrigen: 20 dígitos — cuenta del cliente
        cuentaDestino: 20 dígitos — cuenta del comercio
        referencia: número de referencia de la transferencia (opcional)
        """
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
        amount: str,
        factura: Optional[str] = None,
    ) -> dict:
        """Verifica un depósito bancario recibido."""
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
        amount: str,
        client: Optional[str] = None,
        email: Optional[str] = None,
        factura: Optional[str] = None,
    ) -> dict:
        """
        Verifica un pago recibido vía Zelle.
        codigobancoComercio: 'BOFA'=Bank of America, 'CHAS'=Chase,
                             'CITI'=Citibank, 'WFBI'=Wells Fargo,
                             'NFBK'=Capital One, 'FTBC'=First Third Bank,
                             'PNCC'=PNC, 'MRMD'=HSBC
        client: Nombre del remitente (validación)
        email:  Email Zelle del remitente (validación adicional)
        """
        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "cid": cid,
            "codigobancoComercio": codigobancoComercio,
            "referencia": referencia,
            "amount": amount,
            "client": client,
            "email": email,
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
        amount: str,
        tipomoneda: str,
        factura: Optional[str] = None,
    ) -> dict:
        """
        Inicia pago con cripto. Genera QR para mostrar al cliente.
        tipomoneda: 'BNB', 'BTC', 'ETH', 'USDT', 'LTC', 'DASH', 'DAI', 'TRXUSDT'
        Returns: 'montocrypto', 'qrurl', 'referencia', 'nombremoneda'
        """
        body = build_xml("request", {
            "cod_afiliacion": self.config.codafiliacion,
            "control": control,
            "amount": amount,
            "tipo_moneda": tipomoneda,
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


# ---------------------------------------------------------------------------
# CÓDIGOS DE RESPUESTA
# ---------------------------------------------------------------------------

CODIGOS_RESPUESTA = {
    "00": "APROBADA",
    "09": "Transacción pendiente",
    "39": "No es cuenta de crédito",
    "51": "Fondos insuficientes",
    "88": "Terminal inválido",
    "91": "Plataforma emisor no disponible",
    "99": "Error / Control no encontrado",
    "XD": "Terminal o Payment no disponible",
    "YQ": "Requiere autenticación 3D Secure",
    "T4": "Fallo procesamiento 3D Secure",
    "PC": "Referencia utilizada en otra compra",
    "GA": "Parámetros de entrada errados",
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
