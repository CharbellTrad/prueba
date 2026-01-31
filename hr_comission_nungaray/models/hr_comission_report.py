
from odoo import api, fields, models

class SaleReport(models.Model):
    _name = "hr.comission.report"
    _description = "Comission Analysis Report"
    _order = 'year, month, comissioner_id desc'

    year = fields.Integer(string="Año", readonly=True, group_operator=False)
    month = fields.Integer(string="Mes", readonly=True, group_operator=False)

    comission_amount_cd = fields.Float(string="Monto de comisión en MXN C/D", readonly=True)
    comission_amount_sd = fields.Float(string="Monto de comisión en MXN S/D", readonly=True)
    comission_bono = fields.Float(string="Bono en MXN")
    comission_amount = fields.Float(string="Monto de comisión en MXN", readonly=True)
    monthly_total = fields.Float(string="Total Mensual", readonly=True)
    monthly_cd_amount = fields.Float(string="Total Mensual C/D", readonly=True)
    monthly_sd_amount = fields.Float(string="Total Mensual S/D", readonly=True)

    comissioner_id = fields.Many2one(comodel_name='hr.employee', string="Comisionista", readonly=True)
    comission_location = fields.Selection(string='Locación', selection=[('mxl','Mexicali'), ('tj','Tijuana')] ,readonly=True)
    
    pos_orders = fields.Char(string='pos_orders')
    

    def action_open_pos_orders(self):
        self.ensure_one()
        months = {
            1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
            5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
            9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
        }
        month_num = int(self.month) if self.month else 0
        month_name = months.get(month_num, 'Desconocido')

        order_ids = []
        if self.pos_orders:
            order_ids = [int(i) for i in str(self.pos_orders).split(',') if i.strip().isdigit()]

        domain = [('id', 'in', order_ids)] if order_ids else []

        title = f"Órdenes POS de {self.comissioner_id.name} del mes de {month_name} {int(self.year) if self.year else ''}"
        return {
            'name': title,
            'type': 'ir.actions.act_window',
            'res_model': 'pos.order',
            'view_mode': 'list,form',
            'target': 'current',
            'domain': domain,
            'context': {},
        }
    

    def _query(self):
        return f"""
                    WITH commission_data AS (
                        SELECT 
                            EXTRACT(YEAR FROM po.date_order) AS year,
                            EXTRACT(MONTH FROM po.date_order) AS month,
                            po.comissioner_id,
                            po.comission_location,
                            
                            -- Determinar tipo de comisión basado en descuentos
                            CASE 
                                WHEN EXISTS (
                                    SELECT 1 FROM pos_order_line pol 
                                    WHERE pol.order_id = po.id AND pol.discount > 0
                                ) THEN 'C/D'
                                ELSE 'S/D'
                            END AS comission_type,
                            
                            -- Convertir monto a MXN (obteniendo currency desde pricelist)
                            CASE 
                                WHEN pl.currency_id = (SELECT id FROM res_currency WHERE name = 'MXN' LIMIT 1)
                                THEN po.amount_total
                                ELSE po.amount_total * COALESCE((
                                    SELECT rate FROM res_currency_rate rcr
                                    WHERE rcr.currency_id = pl.currency_id 
                                        AND rcr.name <= po.date_order
                                        AND rcr.company_id = po.company_id
                                    ORDER BY rcr.name DESC LIMIT 1
                                ), 1.0)
                            END AS amount_mxn,
                            
                            po.id as order_id
                        FROM pos_order po
                        LEFT JOIN product_pricelist pl ON po.pricelist_id = pl.id
                        WHERE po.comissioner_id IS NOT NULL 
                            AND po.comission_location IS NOT NULL
                            AND po.state IN ('paid', 'done', 'invoiced')
                            AND po.refunded_order_id_stored IS NULL  -- Excluir órdenes que SON devoluciones
                            AND po.refund_orders_count_stored = 0     -- Excluir órdenes que TIENEN devoluciones
                            -- Excluir órdenes "a crédito" (A cuenta del cliente)
                            AND NOT EXISTS (
                                SELECT 1 FROM pos_payment pp
                                INNER JOIN pos_payment_method ppm ON pp.payment_method_id = ppm.id
                                WHERE pp.pos_order_id = po.id 
                                    AND LOWER(ppm.name::text) LIKE '%%cuenta%%cliente%%'
                            )
                    ),
                    commission_aggregated AS (
                        SELECT 
                            year,
                            month,
                            comissioner_id,
                            comission_location,
                            SUM(amount_mxn) AS total_amount,
                            SUM(CASE WHEN comission_type = 'C/D' THEN amount_mxn ELSE 0 END) AS cd_amount,
                            SUM(CASE WHEN comission_type = 'S/D' THEN amount_mxn ELSE 0 END) AS sd_amount,
                            ARRAY_AGG(order_id) AS orders
                        FROM commission_data
                        GROUP BY 
                            year,
                            month,
                            comissioner_id,
                            comission_location
                    ),
                    commission_rates AS (
                        SELECT 
                            year,
                            month,
                            comissioner_id,
                            comission_location,
                            total_amount AS monthly_total,
                            cd_amount AS monthly_cd_amount,
                            sd_amount AS monthly_sd_amount,
                            orders,

                            CASE 
                                WHEN comission_location = 'mxl' THEN
                                    CASE 
                                        WHEN total_amount >= 441000 THEN 0.002
                                        ELSE 0
                                    END
                                ELSE -- Para otras ubicaciones
                                    CASE 
                                        WHEN total_amount >= 681000 THEN 0.002
                                        ELSE 0
                                    END
                            END AS cd_rate,

                            CASE 
                                WHEN comission_location = 'mxl' THEN
                                    CASE 
                                        WHEN total_amount >= 561000 THEN 0.004
                                        WHEN total_amount >= 441000 THEN 0.0024
                                        ELSE 0
                                    END
                                ELSE -- Para otras ubicaciones
                                    CASE 
                                        WHEN total_amount >= 800000 THEN 0.004
                                        WHEN total_amount >= 681000 THEN 0.0024
                                        ELSE 0
                                    END
                            END AS sd_rate,
                            
                            CASE 
                                WHEN comission_location = 'mxl' THEN
                                    CASE 
                                        WHEN total_amount > 1200000 THEN 5000
                                        WHEN total_amount > 1101000 THEN 3500
                                        WHEN total_amount > 961000 THEN 2500
                                        WHEN total_amount > 761000 THEN 1500
                                        ELSE 0
                                    END
                                ELSE -- Para otras ubicaciones
                                    CASE 
                                        WHEN total_amount > 1800000 THEN 5000
                                        WHEN total_amount > 1500000 THEN 4000
                                        WHEN total_amount > 1300000 THEN 3000
                                        WHEN total_amount > 1150000 THEN 2000
                                        WHEN total_amount > 1000000 THEN 1000
                                        ELSE 0
                                    END
                            END AS bonus_amount
                            
                        FROM commission_aggregated

                    )

                    SELECT 
                        ROW_NUMBER() OVER(ORDER BY year DESC, month DESC, comissioner_id) AS id,
                        year,
                        month,
                        comissioner_id,
                        comission_location,
                        
                        -- Comisión C/D calculada
                        ROUND((monthly_cd_amount * cd_rate)::NUMERIC, 2) AS comission_amount_cd,
                        
                        -- Comisión S/D calculada
                        ROUND((monthly_sd_amount * sd_rate)::NUMERIC, 2) AS comission_amount_sd,
                        
                        -- Bono
                        bonus_amount AS comission_bono,
                        
                        -- Total de comisiones (C/D + S/D + Bono)
                        ROUND(
                            (monthly_cd_amount * cd_rate + monthly_sd_amount * sd_rate + bonus_amount)::NUMERIC, 
                            2
                        ) AS comission_amount,

                        monthly_total,
                        monthly_cd_amount,
                        monthly_sd_amount,
                        ARRAY_TO_STRING(orders, ',') AS pos_orders

                        
                        FROM commission_rates
                        ORDER BY year DESC, month DESC, comissioner_id
                """

    @property
    def _table_query(self): 
        return self._query()