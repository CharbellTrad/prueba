from odoo import http
from odoo.http import request
import re
import logging
import json

_logger = logging.getLogger(__name__)


class TorofanWebhookController(http.Controller):

    @http.route('/torofan/register/new_client', type='http', auth='public', methods=['POST'], csrf=False)
    def register_new_client(self, **kwargs):
        """
        Endpoint para registrar nuevos clientes desde la app Torofan
        
        Autenticación:
        - Via header: Authorization: Bearer <token>
        - Via URL param: ?token=<token>
        
        Payload esperado:
        {
            "new_clients": [{
                "name": "Juan Pérez",
                "email": "juan@example.com",
                "phone": "+525512345678"
            }]
        }
        """
        try:
            # 1. Validar autenticación
            auth_result = self._validate_authentication(request)
            if not auth_result['success']:
                return request.make_json_response(auth_result)

            # 2. Obtener configuración
            config = request.env['torofan.config'].sudo().search([], limit=1)
            if not config:
                return request.make_json_response(self._error_response(
                    'server_error',
                    'Configuración de Torofan no encontrada'
                ))

            # 3. Extraer datos del payload
            payload = json.loads(request.httprequest.get_data())
            clients_data = payload.get('new_clients', [])
            
            if not clients_data:
                return request.make_json_response(self._error_response(
                    'validation_error',
                    'No se proporcionaron datos de clientes',
                    'new_clients'
                ))

            results = []
            
            # 4. Procesar cada cliente
            for client in clients_data:
                result = self._process_client(client, config)
                results.append(result)

            # Si solo hay un cliente, retornar su resultado directamente
            if len(results) == 1:
                return request.make_json_response(results[0])
            
            # Si hay múltiples, retornar array
            return request.make_json_response({
                'success': True,
                'results': results
            })

        except Exception as e:
            _logger.exception("Error inesperado en registro de Torofan")
            return request.make_json_response(self._error_response(
                'server_error',
                f'Error de conexión. Contactar soporte de Torofan: {str(e)}'
            ))

    def _validate_authentication(self, request):
        """Valida el token de autenticación"""
        config = request.env['torofan.config'].sudo().search([], limit=1)
        
        if not config:
            return self._error_response(
                'server_error',
                'Configuración de Torofan no encontrada'
            )

        # Intentar obtener token del header
        auth_header = request.httprequest.headers.get('Authorization', '')
        token = None
        
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]  # Remover "Bearer "
        else:
            # Intentar obtener del parámetro URL
            token = request.httprequest.args.get('token')

        if not token:
            return self._error_response(
                'authentication_error',
                'Token de acceso no proporcionado'
            )

        if token != config.access_token:
            return self._error_response(
                'authentication_error',
                'Token de acceso inválido'
            )

        return {'success': True}

    def _process_client(self, client, config):
        """Procesa el registro de un cliente individual"""
        try:
            # Validaciones
            validation = self._validate_client_data(client)
            if not validation['success']:
                return validation

            # Verificar duplicados por email o teléfono
            email = client.get('email', '').strip()
            phone = client.get('phone', '').strip()
            
            existing_lead = request.env['crm.lead'].sudo().search([
                '|',
                ('email_from', '=', email),
                ('phone', '=', phone)
            ], limit=1)
            
            if existing_lead:
                return self._error_response(
                    'validation_error',
                    f'Ya existe un registro con este email o teléfono (Oportunidad: {existing_lead.name})',
                    'email' if existing_lead.email_from == email else 'phone'
                )

            # Crear oportunidad en CRM
            lead_vals = {
                'name': client.get('name'),  # Solo el nombre
                'contact_name': client.get('name'),
                'email_from': email,
                'phone': phone,
                'type': 'opportunity',
                'from_torofan': True,
            }

            lead = request.env['crm.lead'].sudo().create(lead_vals)
            
            # El cupón se crea automáticamente en el método create del modelo
            # Obtener información del cupón creado
            coupon = lead.torofan_coupon_id
            
            if not coupon:
                _logger.warning(f"No se pudo crear cupón para lead {lead.id}")
                # Aún así retornamos éxito porque el lead se creó
                return self._success_response(lead, None, config)

            return self._success_response(lead, coupon, config)

        except Exception as e:
            _logger.exception(f"Error al procesar cliente: {str(e)}")
            return self._error_response(
                'server_error',
                f'Error al procesar registro: {str(e)}'
            )

    def _validate_client_data(self, client):
        """Valida los datos del cliente"""
        name = client.get('name', '').strip()
        email = client.get('email', '').strip()
        phone = client.get('phone', '').strip()

        # Validar nombre (debe tener formato "Nombre Apellido")
        if not name or ' ' not in name:
            return self._error_response(
                'validation_error',
                "El nombre debe tener formato 'Nombre Apellido'",
                'name'
            )

        # Validar email (debe contener @ y tener formato básico)
        email_regex = r'^[^@]+@[^@]+\.[^@]+$'
        if not email or not re.match(email_regex, email):
            return self._error_response(
                'validation_error',
                "El correo electrónico debe contener '@' y tener formato válido",
                'email'
            )

        # Validar teléfono (debe tener código de país +1 o +52 y 10 dígitos)
        phone_regex = r'^\+?(1|52)\d{10}$'
        if not phone or not re.match(phone_regex, phone):
            return self._error_response(
                'validation_error',
                "El teléfono debe tener 10 dígitos con código de país +1 (EEUU) o +52 (MX)",
                'phone'
            )

        return {'success': True}

    def _success_response(self, lead, coupon, config):
        """Genera respuesta de éxito"""
        response = {
            'success': True,
            'message': 'Registro exitoso',
            'data': {
                'lead_id': lead.id,
                'lead_name': lead.name,
            }
        }

        if coupon:
            response['data'].update({
                'coupon_code': coupon.code,
                'discount_percentage': config.program_discount_percentage if config else 0,
                'minimum_amount': config.program_minimum_amount if config else 0,
                'expiration_date': coupon.expiration_date.strftime('%Y-%m-%d') if coupon.expiration_date else None,
                'company_name': config.program_company_name,
                'program_name': config.loyalty_program_id.name if config.loyalty_program_id else None,
            })

        return response

    def _error_response(self, error_type, message, field=None):
        """Genera respuesta de error"""
        response = {
            'success': False,
            'error_type': error_type,
            'message': message,
        }
        
        if field:
            response['field'] = field

        return response
