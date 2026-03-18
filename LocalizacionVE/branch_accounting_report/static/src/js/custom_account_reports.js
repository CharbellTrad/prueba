odoo.define('branch_accounting_report.account_report_generic', function (require) {
    'use strict';

    var core = require('web.core');
    var RelationalFields = require('web.relational_fields');
    var StandaloneFieldManagerMixin = require('web.StandaloneFieldManagerMixin');
    var { WarningDialog } = require("@web/legacy/js/_deprecated/crash_manager_warning_dialog");
    var Widget = require('web.Widget');
    var accountReportsWidget = require('account_reports.account_report');
    var QWeb = core.qweb;
    var _t = core._t;

    var M2MBranchFilters = Widget.extend(StandaloneFieldManagerMixin, {
        /**
         * @constructor
         * @param {Object} fields
         */
        init: function (parent, fields, change_event) {
            this._super.apply(this, arguments);
            StandaloneFieldManagerMixin.init.call(this);
            this.fields = fields;
            this.widgets = {};
            this.change_event = change_event;
        },
        /**
         * @override
         */
        willStart: function () {
            var self = this;
            var defs = [this._super.apply(this, arguments)];
            _.each(this.fields, function (field, fieldName) {
                defs.push(self._makeM2MWidget(field, fieldName));
            });
            return Promise.all(defs);
        },
        /**
         * @override
         */
        start: function () {
            var self = this;
            var $content = $(QWeb.render("m2mWidgetTable", {fields: this.fields}));
            self.$el.append($content);
            _.each(this.fields, function (field, fieldName) {
                self.widgets[fieldName].appendTo($content.find('#'+fieldName+'_field'));
            });
            return this._super.apply(this, arguments);
        },
    
        //--------------------------------------------------------------------------
        // Private
        //--------------------------------------------------------------------------
    
        /**
         * This method will be called whenever a field value has changed and has
         * been confirmed by the model.
         *
         * @private
         * @override
         * @returns {Promise}
         */
        _confirmChange: function () {
            var self = this;
            var result = StandaloneFieldManagerMixin._confirmChange.apply(this, arguments);
            var data = {};
            _.each(this.fields, function (filter, fieldName) {
                data[fieldName] = self.widgets[fieldName].value.res_ids;
            });
            this.trigger_up(this.change_event, data);
            return result;
        },
        /**
         * This method will create a record and initialize M2M widget.
         *
         * @private
         * @param {Object} fieldInfo
         * @param {string} fieldName
         * @returns {Promise}
         */
        _makeM2MWidget: function (fieldInfo, fieldName) {
            var self = this;
            var options = {};
            options[fieldName] = {
                options: {
                    no_create_edit: true,
                    no_create: true,
                }
            };
            return this.model.makeRecord(fieldInfo.modelName, [{
                fields: [{
                    name: 'id',
                    type: 'integer',
                }, {
                    name: 'display_name',
                    type: 'char',
                }],
                name: fieldName,
                relation: fieldInfo.modelName,
                type: 'many2many',
                value: fieldInfo.value,
            }], options).then(function (recordID) {
                self.widgets[fieldName] = new RelationalFields.FieldMany2ManyTags(self,
                    fieldName,
                    self.model.get(recordID),
                    {mode: 'edit',}
                );
                self._registerWidget(recordID, fieldName, self.widgets[fieldName]);
            });
        },
    });

    var accountReportsWidget = accountReportsWidget.accountReportsWidget.include({
       
        custom_events: _.extend({}, accountReportsWidget.accountReportsWidget.prototype.custom_events, {
            'branch_filter_changed': function (ev) {
                var self = this;
                self.report_options.branch_ids = ev.data.branch_ids;
                return self.reload().then(function () {
                    self.$searchview_buttons.find('.account_branch_filter').click();
                });
            },
        }),

        render_searchview_buttons: function () {
            var self = this;
            self._super();
            if (this.report_options.branch) {
                if (!this.branch_m2m_filter) {
                    var fields = {};
                    if ('branch_ids' in this.report_options) {
                        fields['branch_ids'] = {
                            label: _t('branch'),
                            modelName: 'res.branch',
                            value: this.report_options.branch_ids.map(Number),
                        };
                    }
                    if (!_.isEmpty(fields)) {
                        this.branch_m2m_filter = new M2MBranchFilters(this, fields, 'branch_filter_changed');
                        this.branch_m2m_filter.appendTo(this.$searchview_buttons.find('.js_account_branch_m2m'));
                    }
                } else {
                    this.$searchview_buttons.find('.js_account_branch_m2m').append(this.branch_m2m_filter.$el);
                }
            }

        },

    });

});
