from odoo import models, fields, api
from datetime import datetime, timedelta
import logging


_logger = logging.getLogger(__name__)


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    from_torofan = fields.Boolean(
        string='Creado desde Torofan',
        readonly=True,
        default=False,
        help='Indica si esta oportunidad fue creada desde la aplicación Torofan'
    )
    
    torofan_coupon_id = fields.Many2one(
        'loyalty.card',
        string='Cupón Torofan',
        readonly=True,
        help='Cupón de descuento generado para esta oportunidad de Torofan'
    )

    @api.model_create_multi
    def create(self, vals_list): # type: ignore
        """
        Sobrescribimos create para manejar la lógica de cupones cuando
        la oportunidad se crea desde Torofan
        """
        leads = super(CrmLead, self).create(vals_list)
        
        for lead in leads:
            if lead.from_torofan:
                # Verificar si hay programa de lealtad configurado
                config = self.env['torofan.config'].sudo().search([], limit=1)
                if config and config.loyalty_program_id:
                    try:
                        # Crear cupón automáticamente solo si hay programa
                        coupon = self._create_torofan_coupon(lead)
                        if coupon:
                            lead.torofan_coupon_id = coupon.id
                            # Enviar email con el cupón
                            self._send_torofan_welcome_email(lead, coupon)
                    except Exception as e:
                        _logger.error(f"Error al crear cupón para lead {lead.id}: {str(e)}")
                else:
                    _logger.info(f"Lead {lead.id} creado sin cupón - no hay programa de lealtad configurado")
        
        return leads

    def _create_torofan_coupon(self, lead):
        """
        Crea un cupón de descuento para la oportunidad de Torofan
        """
        config = self.env['torofan.config'].sudo().search([], limit=1)
        
        if not config:
            _logger.warning("No se encontró configuración de Torofan")
            return False
        
        if not config.loyalty_program_id:
            _logger.warning("No hay programa de lealtad configurado en Torofan")
            return False
        
        if not config.is_program_active:
            _logger.warning(f"Intento de crear cupón para programa no activo (vencido o no iniciado): {config.loyalty_program_id.name}")
            return False

        # Generar código único para el cupón
        import uuid
        coupon_code = f"TOROFAN-{uuid.uuid4().hex[:8].upper()}"
        
        # Calcular fecha de expiración basada en configuración
        expiration_date = False
        if config.coupon_validity_value > 0:
            today = fields.Date.context_today(self)
            
            if config.coupon_validity_unit == 'days':
                expiration_date = today + timedelta(days=config.coupon_validity_value)
            elif config.coupon_validity_unit == 'months':
                # Aproximación de meses a 30 días para simplificar
                expiration_date = today + timedelta(days=config.coupon_validity_value * 30)
            elif config.coupon_validity_unit == 'years':
                expiration_date = today + timedelta(days=config.coupon_validity_value * 365)
        
        # Crear el cupón
        coupon_vals = {
            'program_id': config.loyalty_program_id.id,
            'code': coupon_code,
            # partner_id se deja vacío porque aún no hay contacto asignado
        }
        
        # Solo agregar expiration_date si existe
        if expiration_date:
            coupon_vals['expiration_date'] = expiration_date
        
        try:
            coupon = self.env['loyalty.card'].sudo().create(coupon_vals)
            _logger.info(f"Cupón {coupon_code} creado exitosamente para lead {lead.id}")
            
            # Agregar 1 punto al cupón
            coupon.sudo().write({'points': 1.0})
            _logger.info(f"Se agregó 1 punto al cupón {coupon_code}")
            
            return coupon
        except Exception as e:
            _logger.error(f"Error al crear cupón: {str(e)}")
            return False

    def _send_torofan_welcome_email(self, lead, coupon):
        """
        Envía el email de bienvenida con el cupón de descuento
        """
        template = self.env.ref('crm_torofan_integration.mail_template_torofan_welcome', raise_if_not_found=False)
        
        if template and lead.email_from:
            try:
                # Verificar que exista al menos un servidor de correo configurado
                if not self.env['ir.mail_server'].sudo().search([], limit=1):
                    _logger.warning(f"No se envió email para lead {lead.id}: no hay servidores de correo saliente configurados en Odoo")
                    return

                # Determinar el email remitente
                email_from = self.env.company.email
                if coupon and coupon.program_id and coupon.program_id.company_id and coupon.program_id.company_id.email:
                    email_from = coupon.program_id.company_id.email
                elif lead.company_id and lead.company_id.email:
                    email_from = lead.company_id.email

                email_values = {
                    'email_to': lead.email_from,
                    'email_from': email_from,
                    'subject': '¡Bienvenido a Torofan! Tu cupón de descuento te espera',
                }
                template.sudo().send_mail(
                    lead.id,
                    force_send=True,
                    email_values=email_values
                )
                _logger.info(f"Email de bienvenida enviado a {lead.email_from}")
            except Exception as e:
                _logger.error(f"Error al enviar email: {str(e)}")


