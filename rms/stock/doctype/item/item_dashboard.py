from frappe import _

def get_data():
	return {
		'heatmap': True,
		'heatmap_message': _('This is based on stock movement. See {0} for details')\
			.format('<a href="#query-report/Stock Ledger">' + _('Stock Ledger') + '</a>'),
		'fieldname': 'item_code',
		'non_standard_fieldnames': {
			'Production Order': 'production_item',
			'BOM': 'item'
		},
		'transactions': [
			{
				'label': _('Groups'),
				'items': ['BOM']
			},
			{
				'label': _('Move'),
				'items': ['Stock Entry']
			},
			{
				'label': _('Manufacture'),
				'items': ['Production Order']
			}
		]
	}
