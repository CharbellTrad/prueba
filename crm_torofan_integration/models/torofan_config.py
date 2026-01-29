from odoo import models, fields, api
from datetime import timedelta
import uuid
import logging

_logger = logging.getLogger(__name__)


class TorofanConfig(models.Model):
    _name = 'torofan.config'
    _description = 'Configuración de Torofan Integration'
    _rec_name = 'name'

    # Nombre de la configuración
    name = fields.Char(
        string='Nombre de Configuración',
        required=True,
        default='Configuración Torofan',
        help='Nombre descriptivo para identificar esta configuración'
    )

    # Solo permitir un registro (Singleton)
    @api.model
    def _get_default_config(self):
        return self.search([], limit=1)

    # Autenticación
    access_token = fields.Char(
        string='Access Token',
        required=True,
        readonly=True,
        default=lambda self: str(uuid.uuid4()),
        help='Token de autenticación para el endpoint de Torofan',
        copy=False
    )
    
    webhook_url = fields.Char(
        string='URL del Endpoint',
        compute='_compute_webhook_url',
        readonly=True,
        help='URL completa del endpoint para configurar en Torofan'
    )

    # Configuración de Cupones
    loyalty_program_id = fields.Many2one(
        'loyalty.program',
        string='Programa de Lealtad',
        required=False,  # Opcional - si no se configura, no se crean cupones
        domain="[('program_type', '=', 'coupons')]",
        help='Programa donde se crearán los cupones de Torofan. Si no se selecciona, solo se creará la oportunidad sin cupón.'
    )
    
    # Campos de Validez del Cupón
    coupon_validity_value = fields.Integer(
        string='Validez del Cupón',
        default=0,
        help='Número de días/meses/años de validez del cupón generado. Dejar en 0 para sin caducidad.'
    )
    
    coupon_validity_unit = fields.Selection([
        ('days', 'Días'),
        ('months', 'Meses'),
        ('years', 'Años')
    ], string='Unidad de Tiempo', required=False)

    @api.onchange('coupon_validity_value')
    def _onchange_coupon_validity_value(self):
        """Si hay valor de validez, por defecto días"""
        if self.coupon_validity_value > 0 and not self.coupon_validity_unit:
            self.coupon_validity_unit = 'days'

    # Estado del Programa
    program_status_alert = fields.Html(
        compute='_compute_program_status',
        string='Alerta de Estado',
        readonly=True
    )

    is_program_active = fields.Boolean(
        compute='_compute_program_status',
        string='Programa Activo',
        store=True
    )
    
    # Campos computados que muestran la configuración del programa
    program_discount_type = fields.Selection(
        related='loyalty_program_id.reward_ids.discount_mode',
        string='Tipo de Descuento',
        readonly=True
    )
    
    program_discount_percentage = fields.Float(
        compute='_compute_program_discount',
        string='Descuento (%)',
        readonly=True,
        help='Porcentaje de descuento configurado en el programa de lealtad'
    )
    
    program_discount_display = fields.Char(
        compute='_compute_program_discount_display',
        string='Descuento (%)',
        readonly=True,
        help='Descuento formateado para mostrar'
    )
    
    program_minimum_amount = fields.Float(
        compute='_compute_program_minimum',
        string='Monto Mínimo',
        readonly=True,
        help='Monto mínimo configurado en el programa de lealtad'
    )
    
    # Campos adicionales del programa
    program_type = fields.Char(
        compute='_compute_program_type',
        string='Tipo de Programa',
        readonly=True
    )
    
    program_date_from = fields.Date(
        compute='_compute_program_dates',
        string='Fecha de Inicio',
        readonly=True
    )
    
    program_date_to = fields.Date(
        compute='_compute_program_dates',
        string='Fecha Final',
        readonly=True
    )
    
    program_limit_usage = fields.Boolean(
        compute='_compute_program_limit',
        string='Límite de Uso',
        readonly=True
    )
    
    program_company_name = fields.Char(
        compute='_compute_program_company',
        string='Empresa',
        readonly=True,
        help='Empresa del programa de lealtad'
    )
    
    program_currency = fields.Char(
        compute='_compute_program_currency',
        string='Moneda',
        readonly=True,
        help='Moneda del programa de lealtad'
    )
    
    program_available_on = fields.Char(
        compute='_compute_program_available',
        string='Disponible en',
        readonly=True
    )

    @api.depends('access_token')
    def _compute_webhook_url(self):
        """Calcula la URL completa del endpoint"""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            if base_url:
                record.webhook_url = f"{base_url}/torofan/register/new_client"
            else:
                record.webhook_url = "/torofan/register/new_client"
    
    @api.depends('loyalty_program_id', 'loyalty_program_id.reward_ids')
    def _compute_program_discount(self):
        """Extrae el porcentaje de descuento del programa"""
        for record in self:
            if record.loyalty_program_id and record.loyalty_program_id.reward_ids:
                reward = record.loyalty_program_id.reward_ids[0]
                if hasattr(reward, 'discount'):
                    record.program_discount_percentage = reward.discount / 100.0
                else:
                    record.program_discount_percentage = 0.0
            else:
                record.program_discount_percentage = 0.0
    
    @api.depends('program_discount_percentage')
    def _compute_program_discount_display(self):
        """Formatea el descuento para mostrar como '10%'"""
        for record in self:
            if record.program_discount_percentage > 0:
                # Convertir de 0.10 a 10%
                percentage_value = record.program_discount_percentage * 100
                record.program_discount_display = f"{int(percentage_value)}%"
            else:
                record.program_discount_display = "-"
    

    @api.depends('loyalty_program_id', 'loyalty_program_id.rule_ids')
    def _compute_program_minimum(self):
        """Extrae el monto mínimo del programa"""
        for record in self:
            if record.loyalty_program_id and record.loyalty_program_id.rule_ids:
                rule = record.loyalty_program_id.rule_ids[0]
                record.program_minimum_amount = rule.minimum_amount if hasattr(rule, 'minimum_amount') else 0.0
            else:
                record.program_minimum_amount = 0.0
    
    @api.depends('loyalty_program_id', 'loyalty_program_id.company_id')
    def _compute_program_company(self):
        """Extrae el nombre de la empresa del programa"""
        for record in self:
            if record.loyalty_program_id and record.loyalty_program_id.company_id:
                record.program_company_name = record.loyalty_program_id.company_id.name
            else:
                record.program_company_name = 'Torofan Store'
    
    @api.depends('loyalty_program_id', 'loyalty_program_id.currency_id')
    def _compute_program_currency(self):
        """Extrae la moneda del programa"""
        for record in self:
            if record.loyalty_program_id and record.loyalty_program_id.currency_id:
                record.program_currency = record.loyalty_program_id.currency_id.name
            else:
                record.program_currency = 'USD'
    
    @api.depends('loyalty_program_id', 'loyalty_program_id.program_type')
    def _compute_program_type(self):
        """Extrae el tipo de programa"""
        for record in self:
            if record.loyalty_program_id:
                # program_type puede ser 'coupons', 'promotion', 'loyalty', etc
                ptype = str(getattr(record.loyalty_program_id, 'program_type', ''))
                type_map = {
                    'coupons': 'Cupones',
                    'promotion': 'Promoción',
                    'loyalty': 'Lealtad',
                    'gift_card': 'Tarjeta de Regalo'
                }
                record.program_type = type_map.get(ptype, ptype.title() if ptype else 'N/A')
            else:
                record.program_type = 'N/A'
    
    @api.depends('loyalty_program_id', 'loyalty_program_id.date_from', 'loyalty_program_id.date_to')
    def _compute_program_dates(self):
        """Extrae las fechas del programa"""
        for record in self:
            if record.loyalty_program_id:
                record.program_date_from = getattr(record.loyalty_program_id, 'date_from', False)
                record.program_date_to = getattr(record.loyalty_program_id, 'date_to', False)
            else:
                record.program_date_from = False
                record.program_date_to = False
    
    @api.depends('loyalty_program_id', 'loyalty_program_id.limit_usage')
    def _compute_program_limit(self):
        """Extrae si tiene límite de uso"""
        for record in self:
            if record.loyalty_program_id:
                record.program_limit_usage = getattr(record.loyalty_program_id, 'limit_usage', False)
            else:
                record.program_limit_usage = False
    
    @api.depends('loyalty_program_id')
    def _compute_program_available(self):
        """Extrae donde está disponible el programa"""
        for record in self:
            if record.loyalty_program_id:
                available = []
                
                # Punto de Venta
                if getattr(record.loyalty_program_id, 'pos_ok', False):
                     available.append('Punto de venta')

                # Ventas
                if getattr(record.loyalty_program_id, 'sale_ok', False):
                     available.append('Ventas')

                # Sitio Web
                if getattr(record.loyalty_program_id, 'ecommerce_ok', False):
                    available.append('Sitio web')
                
                record.program_available_on = ', '.join(available) if available else 'N/A'
            else:
                record.program_available_on = 'N/A'

    @api.depends('loyalty_program_id', 'program_date_to', 'program_date_from')
    def _compute_program_status(self):
        """Calcula si el programa está activo, por vencer o aún no inicia"""
        for record in self:
            record.is_program_active = True
            record.program_status_alert = False
            
            if not record.loyalty_program_id:
                record.is_program_active = False
                continue
            
            today = fields.Date.today()
            date_from = record.program_date_from
            date_to = record.program_date_to
            
            # Si aún no inicia
            if date_from and today < date_from:
                record.is_program_active = False
                record.program_status_alert = """
                    <div class="alert alert-warning" role="alert">
                        <i class="fa fa-clock-o"></i> 
                        <strong>¡Programa No Iniciado!</strong> 
                        Este programa de lealtad iniciará el %s. 
                        No se generarán cupones hasta esa fecha.
                    </div>
                """ % date_from.strftime('%d/%m/%Y')
                continue

            if not date_to:
                continue
            
            # Si ya venció
            if date_to < today:
                record.is_program_active = False
                record.program_status_alert = """
                    <div class="alert alert-danger" role="alert">
                        <i class="fa fa-exclamation-triangle"></i> 
                        <strong>¡Programa Finalizado!</strong> 
                        Este programa de lealtad ha finalizado el %s. 
                        No se generarán más cupones.
                    </div>
                """ % date_to.strftime('%d/%m/%Y')
                
            # Si vence en 7 días o menos
            elif date_to <= (today + timedelta(days=7)):
                record.program_status_alert = """
                    <div class="alert alert-warning" role="alert">
                        <i class="fa fa-clock-o"></i> 
                        <strong>¡Finaliza Pronto!</strong> 
                        Este programa finalizará el %s.
                    </div>
                """ % date_to.strftime('%d/%m/%Y')



    @api.model_create_multi
    def create(self, vals_list):
        """Override create to set default name with ID"""
        records = super(TorofanConfig, self).create(vals_list)
        for record in records:
            if not record.name or record.name == 'Configuración Torofan':
                record.name = f'Configuración Torofan {record.id}'
        return records

    def action_generate_token(self):
        """Genera un nuevo access token"""
        for record in self:
            new_token = str(uuid.uuid4())
            record.write({'access_token': new_token})
            _logger.info("Nuevo access token generado para Torofan")
        
        # Mostrar notificación y recargar
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.model
    def get_config(self):
        """Obtiene la configuración (singleton)"""
        config = self.search([], limit=1)
        if not config:
            # Crear configuración por defecto si no existe
            config = self.create({
                'access_token': str(uuid.uuid4()),
            })
        return config

