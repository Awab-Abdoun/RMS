from __future__ import unicode_literals

# mappings for table dumps
# "remember to add indexes!"

data_map = {
	# Stock
	"Item": {
		"columns": ["name", "if(item_name=name, '', item_name) as item_name", "description",
			"item_group as parent_item_group"],
		# "conditions": ["docstatus < 2"],
		"order_by": "name",
		"links": {
			"parent_item_group": ["Item Group", "name"]
		}
	},
	"Item Group": {
		"columns": ["name", "parent_item_group"],
		# "conditions": ["docstatus < 2"],
		"order_by": "lft"
	},
	"Project": {
		"columns": ["name"],
		"conditions": ["docstatus < 2"],
		"order_by": "name"
	},
	"Warehouse": {
		"columns": ["name"],
		"conditions": ["docstatus < 2"],
		"order_by": "name"
	},
	"Stock Ledger Entry": {
		"columns": ["name", "posting_date", "posting_time", "item_code", "warehouse",
			"actual_qty as qty", "voucher_type", "voucher_no", "project",
			"qty_after_transaction"],
		"order_by": "posting_date, posting_time, name",
		"links": {
			"item_code": ["Item", "name"],
			"warehouse": ["Warehouse", "name"],
			"project": ["Project", "name"]
		},
		"force_index": "posting_sort_index"
	},
	"Stock Entry": {
		"columns": ["name", "purpose"],
		"conditions": ["docstatus=1"],
		"order_by": "posting_date, posting_time, name",
	},
	"Production Order": {
		"columns": ["name", "production_item as item_code",
			"(qty - produced_qty) as qty",
			"fg_warehouse as warehouse"],
		"conditions": ["docstatus=1", "status != 'Stopped'", "ifnull(fg_warehouse, '')!=''",
			"qty > produced_qty"],
		"links": {
			"item_code": ["Item", "name"],
			"warehouse": ["Warehouse", "name"]
		},
	},
	"Material Request Item": {
		"columns": ["item.name as name", "item_code", "warehouse",
			"(qty - ordered_qty) as qty"],
		"from": "`tabMaterial Request Item` item, `tabMaterial Request` main",
		"conditions": ["item.parent = main.name", "main.docstatus=1", "main.status != 'Stopped'",
			"ifnull(warehouse, '')!=''", "qty > ordered_qty"],
		"links": {
			"item_code": ["Item", "name"],
			"warehouse": ["Warehouse", "name"]
		},
	},

	# Manufacturing
	"Production Order": {
		"columns": ["name","status","creation","planned_start_date","planned_end_date","status","actual_start_date","actual_end_date", "modified"],
		"conditions": ["docstatus = 1"],
		"order_by": "creation"
	}
}
