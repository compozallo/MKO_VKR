# MKO_opt.py (functional part)
import numpy as np
import yadisk
import pandas as pd
import os
import io


class ParetoOptimizer:
    def __init__(self):
        # Основные критерии оптимизации
        self.criteria_names = [
            'Мощность насосов (кВт) ↑',
            'Давление на выходе (атм) ↑',
            'Износ оборудования (%) ↓ [0-100]',
            'Затраты на ТО (руб/ч) ↓',
            'Возраст оборудования (лет) ↓',
            'Общая эффективность ↑'
        ]

        # Параметры насоса
        self.pump_params = {
            'КПД насоса (%) ↑ [0-100]': 85,
            'Макс. давление насоса (атм)': 25,
            'Минимальный расход (м3/ч)': 10,
            'Макс. расход (м3/ч)': 50
        }

        self.num_criteria = len(self.criteria_names)

        # Ограничения для критериев
        self.criteria_limits = {
            'Износ оборудования (%) ↓ [0-100]': (0, 100),
            'Давление на выходе (атм) ↑': (0, 25),
            'Мощность насосов (кВт) ↑': (0, 100)
        }

        # Инициализация переменных
        self.solutions = None
        self.pareto_front = None
        self.optimal_point = None
        self.normalized = None
        self.current_values = None
        self.objectives = None

        # Коэффициенты для расчета системы
        self.system_params = {
            'hydraulic_coeff': 0.85,
            'pump_efficiency_coeff': 0.6,
            'wear_impact': 0.3,
            'maintenance_impact': 0.2,
            'age_impact': 0.15,
            'productivity_coeff': 0.12,
            'pressure_factor': 0.5
        }

        # Прогнозные данные
        self.last_forecast_value = None
        self.load_forecast_data()

    def load_forecast_data(self):

        # Параметры
        TOKEN = "y0__xDypu3yARjTsTcgx67a-RJgY8JQajMm1lnIvrfxvQbbjE-r-g"  # ваш OAuth-токен
        remote_file_path = "/ВКР/forecast.csv"  # путь к файлу на Яндекс.Диске

        # Подключение
        y = yadisk.YaDisk(token=TOKEN)

        # Проверка токена
        if not y.check_token():
            raise Exception("Ошибка токена! Проверьте правильность доступа.")

        # Чтение файла в память
        buffer = io.BytesIO()
        y.download(remote_file_path, buffer)
        buffer.seek(0)  # Обязательно перемотать в начало!

        # Чтение CSV напрямую в pandas
        df_forecast = pd.read_csv(buffer)



        # Просмотр
        print("Прогнозированные данные:")
        print(df_forecast.head())
        self.last_forecast_value = float(df_forecast.iloc[-1]['val'])

    def calculate_system_efficiency(self, params):
        """Расчет КПД системы"""
        pump_efficiency = params['КПД насоса (%) ↑ [0-100]'] / 100
        wear_impact = (100 - params['Износ оборудования (%) ↓ [0-100]']) / 100
        maintenance_impact = 1 - (params['Затраты на ТО (руб/ч) ↓'] / 2000)
        age_impact = 1 - (params['Возраст оборудования (лет) ↓'] / 20)

        forecast_impact = 0
        if self.last_forecast_value:
            forecast_impact = (self.last_forecast_value - 50) / 100

        system_efficiency = (
            pump_efficiency * self.system_params['pump_efficiency_coeff'] +
            self.system_params['hydraulic_coeff'] * (1 - self.system_params['pump_efficiency_coeff']) -
            wear_impact * self.system_params['wear_impact'] -
            (1 - maintenance_impact) * self.system_params['maintenance_impact'] -
            (1 - age_impact) * self.system_params['age_impact'] +
            forecast_impact * 0.1
        )

        return max(0, min(1, system_efficiency)) * 100

    def calculate_productivity(self, power, efficiency, pressure):
        """Расчет производительности системы (т/ч)"""
        base_productivity = power * (efficiency / 100) * self.system_params['productivity_coeff']
        pressure_factor = 1 + (pressure / self.pump_params['Макс. давление насоса (атм)']) * self.system_params['pressure_factor']
        return base_productivity * pressure_factor

    def calculate_overall_efficiency(self, productivity, system_efficiency):
        """Расчет общей эффективности"""
        return (productivity * 0.4 + system_efficiency * 0.6) * 0.9

    def generate_solutions(self, num_solutions, input_values):
        """Генерация решений"""
        self.current_values = input_values.copy()
        self.solutions = np.zeros((num_solutions, self.num_criteria))

        # Генерация случайных решений в пределах допустимых границ
        for i, name in enumerate(self.criteria_names):
            current_val = input_values[name]

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

        # Расчет производных параметров
        system_efficiencies = []
        productivities = []
        overall_efficiencies = []

        for sol in self.solutions:
            params = dict(zip(self.criteria_names, sol))
            params.update(self.pump_params)

            # Расчет КПД системы
            eff = self.calculate_system_efficiency(params)
            system_efficiencies.append(eff)

            # Расчет производительности
            power = params['Мощность насосов (кВт) ↑']
            pump_eff = params['КПД насоса (%) ↑ [0-100]']
            pressure = params['Давление на выходе (атм) ↑']
            prod = self.calculate_productivity(power, pump_eff, pressure)
            productivities.append(prod)

            # Расчет общей эффективности
            overall_eff = self.calculate_overall_efficiency(prod, eff)
            overall_efficiencies.append(overall_eff)

        # Добавляем расчетные параметры в objectives
        self.objectives = np.column_stack([
            productivities,  # Производительность (т/ч)
            system_efficiencies,  # КПД системы (%)
            overall_efficiencies  # Общая эффективность
        ])

        # Сначала строим все решения
        is_efficient = self._find_pareto_front(self.objectives[:, :2])  # Используем только производительность и КПД
        self.pareto_front = self.objectives[is_efficient]

        # Находим оптимальное решение как точку с максимальной общей эффективностью
        if len(self.pareto_front) > 0:
            optimal_idx = np.argmax(self.pareto_front[:, 2])  # Индекс с максимальной общей эффективностью
            self.optimal_point = self.pareto_front[optimal_idx]

        return productivities, system_efficiencies, overall_efficiencies

    def _find_pareto_front(self, points):
        """Улучшенный алгоритм нахождения Парето-фронта (для максимизации обоих критериев)"""
        # Сортируем точки по убыванию первого критерия (производительности)
        sorted_indices = np.argsort(-points[:, 0])
        sorted_points = points[sorted_indices]
        
        pareto_indices = []
        max_eff = -np.inf
        
        for i in range(len(sorted_points)):
            current_eff = sorted_points[i, 1]  # Текущий КПД
            
            # Если текущий КПД больше максимального найденного, добавляем в Парето-фронт
            if current_eff > max_eff:
                pareto_indices.append(sorted_indices[i])
                max_eff = current_eff
        
        # Создаем маску для всех точек
        is_efficient = np.zeros(points.shape[0], dtype=bool)
        is_efficient[pareto_indices] = True
        
        return is_efficient

    def find_closest_solution(self, x, y):
        """Поиск ближайшего решения"""
        if self.solutions is None:
            return None

        distances = np.sqrt(
            (self.objectives[:, 0] - x)**2 +
            (self.objectives[:, 1] - y)**2
        )
        return np.argmin(distances)

    def get_recommendations(self, solution_idx=None):
        """Генерация рекомендаций"""
        if solution_idx is None:
            current_values = self.current_values
        else:
            current_values = dict(zip(self.criteria_names, self.solutions[solution_idx]))

        recommendations = []

        # Рекомендации по основным параметрам
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

        # Расчет производных параметров для рекомендаций
        params = {**current_values, **self.pump_params}
        system_eff = self.calculate_system_efficiency(params)
        productivity = self.calculate_productivity(
            params['Мощность насосов (кВт) ↑'],
            params['КПД насоса (%) ↑ [0-100]'],
            params['Давление на выходе (атм) ↑']
        )
        
        recommendations.append(f"Расчетный КПД системы: {system_eff:.1f}%")
        recommendations.append(f"Расчетная производительность: {productivity:.1f} т/ч")

        # Сравнение с оптимальным решением
        if self.optimal_point is not None and solution_idx is not None:
            current_prod = self.objectives[solution_idx, 0]
            current_eff = self.objectives[solution_idx, 1]
            optimal_prod = self.optimal_point[0]
            optimal_eff = self.optimal_point[1]
            
            if current_prod < optimal_prod and current_eff < optimal_eff:
                recommendations.append("⚠️ Решение можно улучшить по обоим критериям (производительность и КПД)")
            elif current_prod < optimal_prod:
                recommendations.append("⚠️ Решение можно улучшить по производительности")
            elif current_eff < optimal_eff:
                recommendations.append("⚠️ Решение можно улучшить по КПД")

        # Рекомендации по насосу
        pump_rec = []
        for name, value in self.pump_params.items():
            if 'КПД' in name:
                if value < 90:
                    pump_rec.append(f"{name}: возможно увеличение до {min(100, value * 1.15):.1f}")
            elif 'давление' in name.lower():
                req_pressure = current_values['Давление на выходе (атм) ↑']
                if value < req_pressure * 1.1:
                    pump_rec.append(f"{name}: рекомендуется запас минимум 10% (требуется {req_pressure * 1.1:.1f} атм)")

        if pump_rec:
            recommendations.append("Рекомендации по насосу:")
            recommendations.extend(pump_rec)

        # Общие рекомендации по эффективности
        if system_eff < 70:
            recommendations.append("Внимание: низкий КПД системы! Рекомендуется проверить износ оборудования и параметры насоса.")
        elif system_eff > 90:
            recommendations.append("Система работает с высокой эффективностью.")

        if productivity < 10:
            recommendations.append("Внимание: низкая производительность! Рекомендуется проверить мощность насосов и давление в системе.")

        return recommendations