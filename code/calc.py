import math
import xlrd
import xlsxwriter
import enum


class MaterialType(enum.Enum):
    A = 'A'
    B = 'B'
    C = 'C'


epsilon = 0.002
_raw_per_production = {MaterialType.A: 0.6, MaterialType.B: 0.66, MaterialType.C: 0.72}
_price_rate = {MaterialType.A: 1.2, MaterialType.B: 1.1, MaterialType.C: 1}
_production_per_unit = {T: _raw_per_production[T] * _price_rate[T] for T in MaterialType}


class Supplier:
    def __init__(self, supplier_id: str, material_type: MaterialType):
        self.id = supplier_id
        self.type = material_type
        self.order_info: list(int) = []
        self.supply_info: list(int) = []
        self.importance = 0.0
        self.supply_capability = 0.0
        self.supply_stability = 0.0
        self._cost_per_production = _production_per_unit[self.type]
        self._under_supply_freq = 0.0
        self._rate_medium = 0.0
        self._rate_medium_neg = 0.0
        self._continuous_char = 0.0
        self._max_productivity = 0.0
        self.raw_index = []
        self.normalized_index = []

    def _calc_under_supply_freq(self):
        count_all = 0
        count_under = 0
        for i in range(len(self.order_info)):
            if self.order_info[i] > 0:
                count_all += 1
                if self.order_info[i] > self.supply_info[i]:
                    count_under += 1
        self._under_supply_freq = count_under / count_all

    def _calc_rate_medium(self):
        q_list = [self.supply_info[i] / self.order_info[i] for i in range(len(self.order_info)) if
                  self.order_info[i] != 0]
        q_list = sorted(q_list)
        self._rate_medium = q_list[len(q_list) // 2]

    def _calc_rate_medium_neg(self):
        q_list = [1 - self.supply_info[i] / self.order_info[i] for i in range(len(self.order_info)) if
                  self.order_info[i] != 0]
        q_list = sorted(q_list)
        self._rate_medium_neg = q_list[len(q_list) // 2]

    def _calc_max_productivity(self):
        best_of_worst = 0
        for i in range(len(self.order_info)):
            if self.order_info[i] > 0:
                if self.order_info[i] > self.supply_info[i]:
                    if self.supply_info[i] > best_of_worst:
                        best_of_worst = self.supply_info[i]
        if best_of_worst == 0:
            best_of_worst = max(self.supply_info)
        self._max_productivity = best_of_worst

    def _calc_continuous_char(self):
        i = 0
        j = i
        w = 2
        c = []
        while j < len(self.order_info):
            while i < len(self.order_info) and self.order_info[i] == 0:
                i += 1
            j = i
            while j < len(self.order_info) and self.order_info[j] > 0:
                j += 1
            if j - i >= w:
                count = 0
                for index in range(i, j - w + 1):
                    is_under = False
                    for k in range(index, index + w):
                        if self.order_info[k] > self.supply_info[k]:
                            is_under = True
                            break
                    if not is_under:
                        count += 1
                c.append(count / (j - i - w + 1))
            i = j
        self._continuous_char = 0 if len(c) == 0 else sum(c) / len(c)

    def calc_raw_index(self):
        self._calc_continuous_char()
        self._calc_rate_medium()
        self._calc_max_productivity()
        self._calc_under_supply_freq()
        self._calc_rate_medium_neg()
        self.raw_index = [self._cost_per_production,
                          self._rate_medium,
                          self._under_supply_freq,
                          self._rate_medium_neg,
                          self._max_productivity,
                          self._continuous_char]


def calc_importance(supplier_group: list[Supplier], positive_list: list[bool]):
    column_n = len(supplier_group[0].raw_index)
    row_n = len(supplier_group)
    raw_max = [max(supplier.raw_index[j] for supplier in supplier_group) for j in range(column_n)]
    raw_min = [min(supplier.raw_index[j] for supplier in supplier_group) for j in range(column_n)]
    normalized_data = [[(1 - epsilon) *
                        (supplier.raw_index[j] - raw_min[j] if positive_list[j]
                         else raw_max[j] - supplier.raw_index[j]) /
                        (raw_max[j] - raw_min[j]) + epsilon for j in range(column_n)]
                       for supplier in supplier_group]
    normalized_sum = [sum([data[j] for data in normalized_data]) for j in range(column_n)]
    var_index = [[data[j] / normalized_sum[j] for j in range(column_n)] for data in normalized_data]
    entropy_list = [-sum([var[j] * math.log(var[j]) for var in var_index]) / math.log(row_n)
                    for j in range(column_n)]
    redundancy_list = [1 - e for e in entropy_list]
    redundancy_sum = sum(redundancy_list)
    weight_list = [g / redundancy_sum for g in redundancy_list]
    dimension_list = [math.sqrt(sum([data[j] * data[j] for data in normalized_data]))
                      for j in range(column_n)]
    std_data = [[weight_list[j] * row[j] / dimension_list[j] for j in range(column_n)]
                for row in normalized_data]
    max_vec = [max(data[j] for data in std_data) for j in range(column_n)]
    min_vec = [min(data[j] for data in std_data) for j in range(column_n)]
    max_distance = [math.sqrt(sum((std_data[i][j] - max_vec[j]) ** 2 for j in range(column_n)))
                    for i in range(row_n)]
    min_distance = [math.sqrt(sum((std_data[i][j] - min_vec[j]) ** 2 for j in range(column_n)))
                    for i in range(row_n)]
    for i in range(row_n):
        supplier_group[i].importance = min_distance[i] / (max_distance[i] + min_distance[i])
    return weight_list


if __name__ == '__main__':
    wb = xlrd.open_workbook('附件1 近5年402家供应商的相关数据.xls')
    ws1 = wb.sheet_by_name('企业的订货量（m³）')
    ws2 = wb.sheet_by_name('供应商的供货量（m³）')
    suppliers = []
    std_index = []
    for i in range(402):
        suppliers.append(Supplier(ws1.cell_value(i + 1, 0), MaterialType(ws1.cell_value(i + 1, 1))))
        suppliers[i].order_info = [int(ws1.cell_value(i + 1, j)) for j in range(2, 242)]
        suppliers[i].supply_info = [int(ws2.cell_value(i + 1, j)) for j in range(2, 242)]
    for s in suppliers:
        std_index.append(s.calc_raw_index())
    print(calc_importance(suppliers, [False, True, False, False, True, True]))
    priority_list = sorted(suppliers, key=lambda _s: _s.importance, reverse=True)
    wb_out = xlsxwriter.Workbook('Result.xlsx')
    sh1 = wb_out.add_worksheet('result')
    sh1.write(0, 0, 'ID')
    sh1.write(0, 1, 'Type')
    sh1.write(0, 2, 'Index')
    for i in range(len(suppliers)):
        sh1.write(i + 1, 0, priority_list[i].id)
        sh1.write(i + 1, 1, priority_list[i].type.value)
        sh1.write(i + 1, 2, format(priority_list[i].importance, '.4f'))
    wb_out.close()
