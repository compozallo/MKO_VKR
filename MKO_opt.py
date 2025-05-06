import numpy as np
import yadisk
import pandas as pd
import io
from typing import Dict, List, Tuple
import matplotlib
matplotlib.use('Agg')

class ParetoOptimizer:
    def __init__(self):
        # Основные критерии оптимизации
        self.criteria_names = [
            'Давление на выходе (атм) ↑',
            'Износ оборудования (%) ↓ [0-100]',
            'Затраты на ТО (руб/ч) ↓',
            'Возраст оборудования (лет) ↓',
            'Общая эффективность ↑',
            'Требуемая производительность (т/ч) ↑'
        ]

        # Параметры насосов
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

        self.num_criteria = len(self.criteria_names)
        self.forecast_data = None  # Инициализация перед вызовом load_forecast_data
        self.load_forecast_data()  # Теперь этот вызов безопасен

        # Ограничения для критериев
        self.criteria_limits = {
            'Износ оборудования (%) ↓ [0-100]': (0, 100),
            'Давление на выходе (атм) ↑': (0, 25),
            'Требуемая производительность (т/ч) ↑': (0, 100)
        }

        # Инициализация переменных
        self.solutions = None
        self.pareto_front = None
        self.optimal_point = None
        self.current_values = None
        self.objectives = None
        self.required_productivity = None

        # Коэффициенты для расчета системы
        self.system_params = {
            'hydraulic_coeff': 0.85,
            'pump_efficiency_coeff': 0.6,
            'wear_impact': 0.3,
            'maintenance_impact': 0.2,
            'age_impact': 0.15,
            'pressure_factor': 0.5,
            'parallel_coeff': 0.9,
            'density': 1000  # Плотность жидкости кг/м3
        }

    def load_forecast_data(self):
        """Загрузка последних 5 прогнозных значений с Яндекс.Диска"""
        try:
            TOKEN = "y0__xDypu3yARjTsTcgx67a-RJgY8JQajMm1lnIvrfxvQbbjE-r-g"
            remote_file_path = "/ВКР/forecast.csv"

            y = yadisk.YaDisk(token=TOKEN)

            if not y.check_token():
                raise Exception("Ошибка токена! Проверьте правильность доступа.")

            buffer = io.BytesIO()
            y.download(remote_file_path, buffer)
            buffer.seek(0)

            # Чтение CSV с явным указанием столбцов
            df_forecast = pd.read_csv(buffer, names=['timestamp', 'val'], header=0)

            # Преобразование timestamp в datetime
            df_forecast['timestamp'] = pd.to_datetime(df_forecast['timestamp'])

            # Сортировка по времени и выбор последних 5 значений
            self.forecast_data = df_forecast.sort_values('timestamp').tail(5)

            print("Последние 5 прогнозных значений успешно загружены:")
            print(self.forecast_data)

        except Exception as e:
            print(f"Ошибка загрузки прогнозных данных: {str(e)}")
            # Создаем тестовые данные если загрузка не удалась
            test_dates = pd.date_range(end=pd.Timestamp.now(), periods=5, freq='10T')
            self.forecast_data = pd.DataFrame({
                'timestamp': test_dates,
                'val': [107.41, 107.44, 106.97, 107.60, 108.61]
            })
            print("Используются тестовые данные")

    def get_forecast_table(self) -> List[Dict]:
        """Получение данных для таблицы прогнозов"""
        if self.forecast_data is None or self.forecast_data.empty:
            return []
        return self.forecast_data.to_dict('records')

    def set_required_productivity(self, value: float):
        """Установка требуемой производительности"""
        self.required_productivity = value
        if self.current_values is not None:
            self.current_values['Требуемая производительность (т/ч) ↑'] = value

    def toggle_pump(self, pump_name: str, state: bool):
        """Включение/выключение насоса"""
        if pump_name in self.pumps:
            self.pumps[pump_name]['Включен'] = state

    def calculate_pump_efficiency(self, pump_params: Dict) -> float:
        """Расчет КПД насоса с учетом его параметров"""
        base_efficiency = pump_params['КПД насоса (%) ↑ [0-100]'] / 100
        wear_impact = (100 - self.current_values['Износ оборудования (%) ↓ [0-100]']) / 100
        age_impact = 1 - (self.current_values['Возраст оборудования (лет) ↓'] / 30)
        return base_efficiency * wear_impact * age_impact

    def calculate_system_efficiency(self, params: Dict) -> float:
        """Расчет общего КПД системы"""
        total_efficiency = 0
        total_weight = 0

        for pump_name, pump in self.pumps.items():
            if not pump['Включен']:
                continue

            pump_eff = self.calculate_pump_efficiency(pump)
            max_flow = pump['Макс. расход (м3/ч)']
            weight = max_flow / sum(p['Макс. расход (м3/ч)'] for p in self.pumps.values() if p['Включен'])

            total_efficiency += pump_eff * weight
            total_weight += weight

        if total_weight == 0:
            return 0

        system_efficiency = total_efficiency / total_weight
        maintenance_impact = 1 - (params['Затраты на ТО (руб/ч) ↓'] / 3000)

        system_efficiency = (
            system_efficiency * self.system_params['pump_efficiency_coeff'] +
            self.system_params['hydraulic_coeff'] * (1 - self.system_params['pump_efficiency_coeff']) -
            (1 - maintenance_impact) * self.system_params['maintenance_impact']
        )

        active_pumps = sum(1 for p in self.pumps.values() if p['Включен'])
        if active_pumps > 1:
            system_efficiency *= self.system_params['parallel_coeff'] ** (active_pumps - 1)

        return max(0, min(1, system_efficiency)) * 100

    def calculate_productivity(self, pressure: float) -> float:
        """Расчет производительности системы (т/ч)"""
        active_pumps = [p for p in self.pumps.values() if p['Включен']]
        if not active_pumps:
            return 0

        total_productivity = 0

        for pump in active_pumps:
            pump_eff = self.calculate_pump_efficiency(pump)
            max_flow = pump['Макс. расход (м3/ч)']
            pressure_factor = 1 - (pressure / pump['Макс. давление насоса (атм)']) * 0.2
            pump_productivity = max_flow * pressure_factor * (pump_eff ** 0.5)

            total_productivity += pump_productivity

        return total_productivity

    def calculate_overall_efficiency(self, productivity: float, system_efficiency: float) -> float:
        """Расчет общей эффективности"""
        req_productivity_impact = 0
        if self.required_productivity:
            req_productivity_impact = 1 - min(1, abs(productivity - self.required_productivity) / self.required_productivity)

        return (productivity * 0.4 + system_efficiency * 0.4 + req_productivity_impact * 0.2) * 0.95

    def generate_solutions(self, num_solutions: int, input_values: Dict):
        """Генерация решений"""
        self.current_values = input_values.copy()
        self.solutions = np.zeros((num_solutions, self.num_criteria))

        for i, name in enumerate(self.criteria_names):
            current_val = input_values.get(name, 0)
            if name in self.criteria_limits:
                min_val, max_val = self.criteria_limits[name]
                self.solutions[:, i] = np.random.uniform(
                    max(min_val, current_val * 0.7),
                    min(max_val, current_val * 1.3),
                    num_solutions
                )
            else:
                self.solutions[:, i] = np.random.normal(
                    current_val,
                    current_val * 0.15,
                    num_solutions
                )

        system_efficiencies = []
        productivities = []
        overall_efficiencies = []

        for sol in self.solutions:
            params = dict(zip(self.criteria_names, sol))
            eff = self.calculate_system_efficiency(params)
            pressure = params['Давление на выходе (атм) ↑']
            prod = self.calculate_productivity(pressure)
            overall_eff = self.calculate_overall_efficiency(prod, eff)

            system_efficiencies.append(eff)
            productivities.append(prod)
            overall_efficiencies.append(overall_eff)

        self.objectives = np.column_stack([productivities, system_efficiencies, overall_efficiencies])
        is_efficient = self._find_pareto_front(self.objectives[:, :2])
        self.pareto_front = self.objectives[is_efficient]

        if len(self.pareto_front) > 0:
            optimal_idx = np.argmax(self.pareto_front[:, 2])
            self.optimal_point = self.pareto_front[optimal_idx]

        return productivities, system_efficiencies, overall_efficiencies

    def _find_pareto_front(self, points: np.ndarray) -> np.ndarray:
        """Нахождение Парето-фронта"""
        sorted_indices = np.argsort(-points[:, 0])
        sorted_points = points[sorted_indices]
        pareto_indices = []
        max_eff = -np.inf

        for i in range(len(sorted_points)):
            if sorted_points[i, 1] > max_eff:
                pareto_indices.append(sorted_indices[i])
                max_eff = sorted_points[i, 1]

        is_efficient = np.zeros(points.shape[0], dtype=bool)
        is_efficient[pareto_indices] = True
        return is_efficient

    def find_closest_solution(self, x: float, y: float) -> int:
        """Поиск ближайшего решения"""
        if self.solutions is None:
            return None
        distances = np.sqrt((self.objectives[:, 0] - x)**2 + (self.objectives[:, 1] - y)**2)
        return np.argmin(distances)

    def get_general_recommendations(self, solution_idx: int = None) -> List[str]:
        """Общие рекомендации по оптимизации"""
        if solution_idx is None:
            current_values = self.current_values
        else:
            current_values = dict(zip(self.criteria_names, self.solutions[solution_idx]))

        recommendations = []

        for name in self.criteria_names:
            current = current_values[name]
            if name in self.criteria_limits:
                min_limit, max_limit = self.criteria_limits[name]
                if '↑' in name and current >= max_limit * 0.95:
                    recommendations.append(f"{name}: значение близко к максимуму ({current:.1f} из {max_limit})")
                elif '↓' in name and current <= min_limit * 1.05:
                    recommendations.append(f"{name}: значение близко к минимуму ({current:.1f} из {min_limit})")
                else:
                    if '↑' in name:
                        rec = f"{name}: можно увеличить до {max_limit:.1f} (текущее {current:.1f})"
                    else:
                        rec = f"{name}: можно уменьшить до {min_limit:.1f} (текущее {current:.1f})"
                    recommendations.append(rec)

        system_eff = self.calculate_system_efficiency(current_values)
        productivity = self.calculate_productivity(
            current_values['Давление на выходе (атм) ↑']
        )

        recommendations.append(f"Текущая производительность: {productivity:.2f} т/ч")
        recommendations.append(f"КПД системы: {system_eff:.1f}%")

        active_pumps = [name for name, p in self.pumps.items() if p['Включен']]
        if not active_pumps:
            recommendations.append("⚠️ Внимание: ни один насос не включен!")
        else:
            recommendations.append(f"Активные насосы: {', '.join(active_pumps)}")

        return recommendations

    def get_forecast_recommendations(self) -> List[str]:
        """Рекомендации для достижения требуемой производительности"""
        if not self.required_productivity:
            return ["Требуемая производительность не задана"]

        recommendations = []
        current_productivity = self.calculate_productivity(
            self.current_values['Давление на выходе (атм) ↑']
        )

        diff = self.required_productivity - current_productivity

        if abs(diff) < 0.1:
            return ["Текущая производительность соответствует требуемой"]

        if diff > 0:
            recommendations.append(f"⚠️ Требуется увеличить производительность на {diff:.2f} т/ч")

            for pump_name, pump in self.pumps.items():
                if not pump['Включен']:
                    recommendations.append(f"• Включить {pump['Название']} для увеличения производительности")

            pressure_increase = diff * 0.3
            new_pressure = min(
                self.criteria_limits['Давление на выходе (атм) ↑'][1],
                self.current_values['Давление на выходе (атм) ↑'] + pressure_increase
            )
            recommendations.append(f"• Увеличить давление до {new_pressure:.1f} атм")

        else:
            recommendations.append(f"⚡ Можно уменьшить производительность на {-diff:.2f} т/ч для экономии энергии")

            if any(pump['Включен'] for pump in self.pumps.values()):
                recommendations.append("• Отключить один из насосов для экономии энергии")

        return recommendations
