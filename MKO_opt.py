import numpy as np
import pandas as pd
import io
from typing import Dict, List, Tuple
import yadisk
from scipy.spatial.distance import euclidean

class ParetoOptimizer:
    def __init__(self):
        self.criteria_names = [
            'Давление на выходе (атм) ↑',
            'Износ оборудования (%) ↓ [0-100]',
            'Затраты на ТО (руб/ч) ↓',
            'Возраст оборудования (лет) ↓',
            'Общая эффективность ↑',
            'Требуемая производительность (т/ч) ↑'
        ]

        self.pumps = {
            'Насос 1': {
                'Название': 'Насос Dab CM-G 100-510',
                'Макс. давление насоса (атм)': 16,
                'Макс. напор (м в ст)': 10.2,
                'Макс. расход (м3/ч)': 120,
                'Макс. потребляемая мощность (кВт)': 4,
                'КПД насоса (%) ↑ [0-100]': 85,
                'Минимальный расход (м3/ч)': 10,
                'Включен': True
            },
            'Насос 2': {
                'Название': 'Насос Dab CM-G 100-1020',
                'Макс. давление насоса (атм)': 16,
                'Макс. напор (м в ст)': 4.9,
                'Макс. расход (м3/ч)': 60,
                'Макс. потребляемая мощность (кВт)': 1,
                'КПД насоса (%) ↑ [0-100]': 75,
                'Минимальный расход (м3/ч)': 5,
                'Включен': False
            }
        }

        self.criteria_limits = {
            'Износ оборудования (%) ↓ [0-100]': (0, 100),
            'Давление на выходе (атм) ↑': (0, 25),
            'Требуемая производительность (т/ч) ↑': (0, 100)
        }

        self.num_criteria = len(self.criteria_names)
        self.forecast_data = None
        self.solutions = None
        self.objectives = None
        self.pareto_front = None
        self.optimal_point = None
        self.current_values = None
        self.required_productivity = None

        self.system_params = {
            'hydraulic_coeff': 0.85,
            'pump_efficiency_coeff': 0.6,
            'wear_impact': 0.3,
            'maintenance_impact': 0.2,
            'age_impact': 0.15,
            'pressure_factor': 0.5,
            'parallel_coeff': 0.9,
            'density': 1000
        }

        self._load_forecast_data()

    def _load_forecast_data(self):
        try:
            TOKEN = "y0__xDypu3yARjTsTcgx67a-RJgY8JQajMm1lnIvrfxvQbbjE-r-g"
            remote_file_path = "/ВКР/forecast.csv"
            y = yadisk.YaDisk(token=TOKEN)
            if not y.check_token():
                raise Exception("Ошибка токена Yandex Disk!")
            buffer = io.BytesIO()
            y.download(remote_file_path, buffer)
            buffer.seek(0)
            df = pd.read_csv(buffer, names=['timestamp', 'val'], header=0)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').tail(5)
            df['val'] = df['val'] / (1_000_000 * 4)
            self.forecast_data = df
        except Exception as e:
            print(f"[WARN] Не удалось загрузить прогноз с Яндекс.Диска: {e}")
            test_dates = pd.date_range(end=pd.Timestamp.now(), periods=5, freq='10min')
            self.forecast_data = pd.DataFrame({
                'timestamp': test_dates,
                'val': [107.41, 107.44, 106.97, 107.60, 108.61]
            })

    def get_forecast_table(self) -> List[Dict]:
        if self.forecast_data is None:
            return []
        return self.forecast_data.to_dict('records')

    def get_forecast_table_html(self) -> str:
        if self.forecast_data is None:
            return "<p>Нет данных прогноза</p>"
        df = self.forecast_data.copy()
        df['val'] = df['val'].round(6)
        return df.to_html(index=False, classes="table table-striped table-bordered")
    
    def get_forecast_recommendations(self) -> list:
        if not self.required_productivity:
            return ["Требуемая производительность не задана"]
        recs = []
        cur_prod = self.calculate_productivity(self.current_values['Давление на выходе (атм) ↑'])
        diff = self.required_productivity - cur_prod
        if abs(diff) < 0.1:
            return ["Текущая производительность соответствует требуемой"]
        if diff > 0:
            recs.append(f"⚠️ Требуется увеличить производительность на {diff:.2f} т/ч")
            for name, pump in self.pumps.items():
                if not pump['Включен']:
                    recs.append(f"• Включить {pump['Название']}")
            pressure_add = diff * 0.3
            new_pressure = min(self.criteria_limits['Давление на выходе (атм) ↑'][1],
                            self.current_values['Давление на выходе (атм) ↑'] + pressure_add)
            recs.append(f"• Увеличить давление до {new_pressure:.1f} атм")
        else:
            recs.append(f"⚡ Можно уменьшить производительность на {-diff:.2f} т/ч для экономии")
            if any(p['Включен'] for p in self.pumps.values()):
                recs.append("• Отключить один из насосов")
        return recs


    def set_required_productivity(self, value: float):
        self.required_productivity = value
        if self.current_values is not None:
            self.current_values['Требуемая производительность (т/ч) ↑'] = value

    def toggle_pump(self, pump_name: str, state: bool):
        if pump_name in self.pumps:
            self.pumps[pump_name]['Включен'] = state

    def calculate_pump_efficiency(self, pump: Dict) -> float:
        base = pump['КПД насоса (%) ↑ [0-100]'] / 100
        wear = (100 - self.current_values['Износ оборудования (%) ↓ [0-100]']) / 100
        age = 1 - (self.current_values['Возраст оборудования (лет) ↓'] / 30)
        return base * wear * age

    def calculate_system_efficiency(self, params: Dict) -> float:
        total, weight = 0, 0
        for pump in self.pumps.values():
            if not pump['Включен']:
                continue
            eff = self.calculate_pump_efficiency(pump)
            flow = pump['Макс. расход (м3/ч)']
            w = flow / sum(p['Макс. расход (м3/ч)'] for p in self.pumps.values() if p['Включен'])
            total += eff * w
            weight += w
        if weight == 0:
            return 0
        system_eff = total / weight
        maint = 1 - (params['Затраты на ТО (руб/ч) ↓'] / 3000)
        system_eff = (
            system_eff * self.system_params['pump_efficiency_coeff'] +
            self.system_params['hydraulic_coeff'] * (1 - self.system_params['pump_efficiency_coeff']) -
            (1 - maint) * self.system_params['maintenance_impact']
        )
        n = sum(p['Включен'] for p in self.pumps.values())
        if n > 1:
            system_eff *= self.system_params['parallel_coeff'] ** (n - 1)
        return max(0, min(1, system_eff)) * 100

    def calculate_productivity(self, pressure: float) -> float:
        total = 0
        for pump in self.pumps.values():
            if not pump['Включен']:
                continue
            eff = self.calculate_pump_efficiency(pump)
            flow = pump['Макс. расход (м3/ч)']
            pf = 1 - (pressure / pump['Макс. давление насоса (атм)']) * 0.2
            total += flow * pf * (eff ** 0.5)
        return total * self.system_params['density'] / 1000

    def calculate_overall_efficiency(self, prod: float, eff: float) -> float:
        impact = 0
        if self.required_productivity:
            impact = 1 - min(1, abs(prod - self.required_productivity) / self.required_productivity)
        return (prod * 0.4 + eff * 0.4 + impact * 0.2) * 0.95

    def generate_solutions(self, num: int, inputs: Dict):
        self.current_values = inputs.copy()
        self.solutions = np.zeros((num, self.num_criteria))
        for i, name in enumerate(self.criteria_names):
            val = inputs.get(name, 0)
            if name in self.criteria_limits:
                min_val, max_val = self.criteria_limits[name]
                self.solutions[:, i] = np.random.uniform(max(min_val, val * 0.7), min(max_val, val * 1.3), num)
            else:
                self.solutions[:, i] = np.random.normal(val, max(val * 0.15, 1e-3), num)
        prods, effs, overalls = [], [], []
        for sol in self.solutions:
            params = dict(zip(self.criteria_names, sol))
            eff = self.calculate_system_efficiency(params)
            prod = self.calculate_productivity(params['Давление на выходе (атм) ↑'])
            over = self.calculate_overall_efficiency(prod, eff)
            prods.append(prod)
            effs.append(eff)
            overalls.append(over)
        self.objectives = np.column_stack([prods, effs, overalls])
        mask = self._find_pareto_front(self.objectives[:, :2])
        self.pareto_front = self.objectives[mask]
        if len(self.pareto_front) > 0:
            self.optimal_point = self.pareto_front[np.argmax(self.pareto_front[:, 2])]

    def _find_pareto_front(self, points: np.ndarray) -> np.ndarray:
        idx = np.argsort(-points[:, 0])
        points = points[idx]
        pareto = []
        max_eff = -np.inf
        for i, p in enumerate(points):
            if p[1] > max_eff:
                pareto.append(idx[i])
                max_eff = p[1]
        result = np.zeros(len(idx), dtype=bool)
        result[pareto] = True
        return result

    def find_closest_solution(self, x: float, y: float) -> int:
        if self.solutions is None:
            return None
        dist = np.sqrt((self.objectives[:, 0] - x) ** 2 + (self.objectives[:, 1] - y) ** 2)
        return int(np.argmin(dist))

    def get_path_to_solution(self, idx: int) -> List[Tuple[float, float]]:
        if idx is None or self.solutions is None:
            return []
        cur = np.array([self.current_values[name] for name in self.criteria_names])
        tgt = self.solutions[idx]
        path = []
        for a in np.linspace(0, 1, 15):
            p = cur * (1 - a) + tgt * a
            params = dict(zip(self.criteria_names, p))
            eff = self.calculate_system_efficiency(params)
            prod = self.calculate_productivity(params['Давление на выходе (атм) ↑'])
            path.append((prod, eff))
        return path

    def get_detailed_recommendations(self, idx: int) -> List[str]:
        if idx is None or self.solutions is None:
            return ["Невозможно сформировать рекомендации"]
        recs = []
        cur = self.current_values
        tgt = dict(zip(self.criteria_names, self.solutions[idx]))
        for name in self.criteria_names:
            c, t = cur[name], tgt[name]
            diff = t - c
            if abs(diff) < 0.01:
                recs.append(f"{name}: оставить без изменений ({c:.2f})")
            else:
                if '↑' in name:
                    action = "увеличить" if diff > 0 else "уменьшить"
                elif '↓' in name:
                    action = "уменьшить" if diff > 0 else "увеличить"
                else:
                    action = "изменить"
                recs.append(f"{name}: {action} с {c:.2f} до {t:.2f} ({'+' if diff > 0 else '-'}{abs(diff):.2f})")
        return recs

    def get_general_recommendations(self, idx: int = None) -> List[str]:
        values = self.current_values if idx is None else dict(zip(self.criteria_names, self.solutions[idx]))
        recs = []
        for name in self.criteria_names:
            val = values[name]
            if name in self.criteria_limits:
                low, high = self.criteria_limits[name]
                if '↑' in name and val >= high * 0.95:
                    recs.append(f"{name}: значение близко к максимуму ({val:.1f} из {high})")
                elif '↓' in name and val <= low * 1.05:
                    recs.append(f"{name}: значение близко к минимуму ({val:.1f} из {low})")
                else:
                    if '↑' in name:
                        recs.append(f"{name}: можно увеличить до {high:.1f} (текущее {val:.1f})")
                    else:
                        recs.append(f"{name}: можно уменьшить до {low:.1f} (текущее {val:.1f})")
        eff = self.calculate_system_efficiency(values)
        prod = self.calculate_productivity(values['Давление на выходе (атм) ↑'])
        recs.append(f"Текущая производительность: {prod:.2f} т/ч")
        recs.append(f"КПД системы: {eff:.1f}%")
        active = [n for n, p in self.pumps.items() if p['Включен']]
        if not active:
            recs.append("⚠️ Ни один насос не включён")
        else:
            recs.append(f"Активные насосы: {', '.join(active)}")
        return recs
    
    def create_radar_chart(self):
        active_params = [
            'Давление на выходе (атм) ↑',
            'Износ оборудования (%) ↓ [0-100]',
            'Затраты на ТО (руб/ч) ↓',
            'Возраст оборудования (лет) ↓',
            'КПД системы (%)',
            'Производительность (т/ч)'
        ]
        current = self.current_values.copy()
        current['КПД системы (%)'] = self.calculate_system_efficiency(current)
        current['Производительность (т/ч)'] = self.calculate_productivity(current['Давление на выходе (атм) ↑'])

        optimal = None
        if self.optimal_point is not None:
            idx = np.argmax(self.pareto_front[:, 2])
            sol = self.solutions[idx]
            optimal = dict(zip(self.criteria_names, sol))
            optimal['КПД системы (%)'] = self.pareto_front[idx, 1]
            optimal['Производительность (т/ч)'] = self.pareto_front[idx, 0]

        cur_norm, opt_norm = [], []
        for p in active_params:
            if p in self.criteria_limits:
                low, high = self.criteria_limits[p]
                cur_norm.append((current[p] - low) / (high - low))
                if optimal:
                    opt_norm.append((optimal[p] - low) / (high - low))
            else:
                cur_norm.append(current[p] / 100)
                if optimal:
                    opt_norm.append(optimal[p] / 100)

        import plotly.graph_objects as go
        fig = go.Figure()
        if optimal:
            fig.add_trace(go.Scatterpolar(
                r=opt_norm, theta=active_params, fill='toself',
                name='Оптимум', opacity=0.5,
                marker=dict(color='orange'),
                fillcolor='rgba(255,165,0,0.2)'
            ))
        fig.add_trace(go.Scatterpolar(
            r=cur_norm, theta=active_params, fill='toself',
            name='Текущие', opacity=0.8,
            marker=dict(color='royalblue'),
            fillcolor='rgba(65,105,225,0.3)'
        ))
        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 1])
            ),
            showlegend=True,
            title='Радарная диаграмма параметров',
            font=dict(family="Arial, sans-serif"),
            margin=dict(l=30, r=30, t=50, b=30)
      )
        return fig.to_html(full_html=False)
