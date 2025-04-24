import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
import base64

class ParetoOptimizer:
    def __init__(self):
        self.criteria_names = [
            'Мощность насосов (кВт) ↑',
            'Давление на выходе (атм) ↑',
            'Потребление тока (А) ↓',
            'Энергопотребление (кВт·ч) ↓',
            'Износ оборудования (%) ↓ [0-100]',
            'Температура двигателя (°C) ↓ [0-120]',
            'Квалификация рабочих (баллы) ↑ [0-10]',
            'КПД насоса (%) ↑ [0-100]',
            'Затраты на ТО (руб/ч) ↓',
            'Возраст оборудования (лет) ↓'
        ]

        self.num_criteria = len(self.criteria_names)

        self.criteria_limits = {
            'Износ оборудования (%) ↓ [0-100]': (0, 100),
            'Температура двигателя (°C) ↓ [0-120]': (0, 120),
            'Квалификация рабочих (баллы) ↑ [0-10]': (0, 10),
            'КПД насоса (%) ↑ [0-100]': (0, 100)
        }

        self.solutions = None
        self.pareto_front = None
        self.optimal_point = None
        self.normalized = None
        self.current_values = None
        self.productivity = None
        self.current_consumption = None

    def calculate_current_consumption(self, power, voltage=380, efficiency=0.9):
        return power / (voltage * efficiency * np.sqrt(3))

    def generate_solutions(self, num_solutions, input_values):
        self.current_values = input_values.copy()
        base = np.array([input_values[name] for name in self.criteria_names])
        self.solutions = np.zeros((num_solutions, self.num_criteria))

        for i, name in enumerate(self.criteria_names):
            current_value = input_values[name]

            if i % 3 == 0:
                values = np.random.normal(current_value, 0.2*current_value, num_solutions)
            elif i % 3 == 1:
                lower, upper = 0.7 * current_value, 1.3 * current_value
                values = np.random.uniform(lower, upper, num_solutions)
            else:
                values = current_value * np.random.beta(2, 5, num_solutions) * 2

            if name in self.criteria_limits:
                min_limit, max_limit = self.criteria_limits[name]
                values = np.clip(values, min_limit, max_limit)

            self.solutions[:, i] = values

        power_idx = self.criteria_names.index('Мощность насосов (кВт) ↑')
        efficiency_idx = self.criteria_names.index('КПД насоса (%) ↑ [0-100]')
        current_consumption = self.calculate_current_consumption(
            self.solutions[:, power_idx],
            efficiency=self.solutions[:, efficiency_idx]/100
        )
        self.solutions[:, 2] = current_consumption

        self.productivity = (
            0.4 * self.solutions[:, 0] +
            0.3 * self.solutions[:, 1] +
            0.2 * self.solutions[:, 7] -
            0.1 * self.solutions[:, 4]
        )

        self.current_consumption = self.solutions[:, 2]

        self.normalized = np.column_stack([
            (self.productivity - np.min(self.productivity)) / (np.max(self.productivity) - np.min(self.productivity)),
            (1 - (self.current_consumption - np.min(self.current_consumption)) /
             (np.max(self.current_consumption) - np.min(self.current_consumption)))
        ])

        is_efficient = np.ones(num_solutions, dtype=bool)
        for i, c in enumerate(self.normalized):
            if is_efficient[i]:
                is_efficient[is_efficient] = np.any(self.normalized[is_efficient] > c, axis=1)
                is_efficient[i] = True

        self.pareto_front = np.column_stack([self.productivity, self.current_consumption])[is_efficient]
        if len(self.pareto_front) > 0:
            self.optimal_point = self.pareto_front[np.argmax(
                self.normalized[is_efficient, 0] + self.normalized[is_efficient, 1]
            )]
        else:
            self.optimal_point = None

        return self.productivity, self.current_consumption

    def find_closest_solution(self, x, y):
        if self.solutions is None:
            return None

        distances = np.sqrt((self.productivity - x)**2 + (self.current_consumption - y)**2)
        closest_idx = np.argmin(distances)
        return closest_idx

    def get_recommendations(self, solution_idx=None):
        if solution_idx is None:
            input_values = self.current_values
        else:
            input_values = {name: self.solutions[solution_idx, i]
                          for i, name in enumerate(self.criteria_names)}

        recommendations = []
        for name in self.criteria_names:
            current = input_values[name]

            if name in self.criteria_limits:
                min_limit, max_limit = self.criteria_limits[name]
                if '↑' in name and current >= max_limit:
                    recommendations.append(f"{name}: уже на максимуме ({max_limit})")
                    continue
                elif '↓' in name and current <= min_limit:
                    recommendations.append(f"{name}: уже на минимуме ({min_limit})")
                    continue

            if '↑' in name:
                rec = f"{name}: +{current*0.15:.1f} (рекомендуется)"
            else:
                rec = f"{name}: -{current*0.15:.1f} (рекомендуется)"
            recommendations.append(rec)

        return recommendations

def create_plot_all(optimizer):
    plt.figure(figsize=(8, 5))
    if optimizer.productivity is not None and optimizer.current_consumption is not None:
        plt.scatter(optimizer.productivity, optimizer.current_consumption,
                   c='gray', s=5, alpha=0.5)

    if optimizer.pareto_front is not None and len(optimizer.pareto_front) > 0:
        pf_prod = optimizer.pareto_front[:, 0]
        pf_current = optimizer.pareto_front[:, 1]
        order = np.argsort(pf_prod)
        plt.plot(pf_prod[order], pf_current[order], 'r--', alpha=0.8, linewidth=1.5)
        if optimizer.optimal_point is not None:
            plt.scatter(optimizer.optimal_point[0], optimizer.optimal_point[1],
                       c='blue', s=100, label='Оптимальное')

    plt.xlabel('Производительность', fontsize=10)
    plt.ylabel('Потребление тока (А)', fontsize=10)
    plt.grid(True, linestyle=':', alpha=0.3)
    plt.legend()
    plt.tight_layout()

    return plot_to_base64(plt)

def create_plot_pareto(optimizer):
    plt.figure(figsize=(8, 5))

    if optimizer.pareto_front is not None and len(optimizer.pareto_front) > 0:
        pf_prod = optimizer.pareto_front[:, 0]
        pf_current = optimizer.pareto_front[:, 1]
        order = np.argsort(pf_prod)
        plt.plot(pf_prod[order], pf_current[order], 'r--', alpha=0.8, linewidth=1.5)
        if optimizer.optimal_point is not None:
            plt.scatter(optimizer.optimal_point[0], optimizer.optimal_point[1],
                       c='blue', s=100, label='Оптимальное')

        if optimizer.productivity is not None and optimizer.current_consumption is not None:
            current_point = (np.mean(optimizer.productivity), np.mean(optimizer.current_consumption))
            plt.scatter(current_point[0], current_point[1],
                       c='green', s=100, marker='s', label='Текущее')
            if optimizer.optimal_point is not None:
                plt.plot([current_point[0], optimizer.optimal_point[0]],
                        [current_point[1], optimizer.optimal_point[1]],
                        'g-', alpha=0.5, linewidth=2)

    plt.xlabel('Производительность', fontsize=10)
    plt.ylabel('Потребление тока (А)', fontsize=10)
    plt.grid(True, linestyle=':', alpha=0.3)
    plt.legend()
    plt.tight_layout()

    return plot_to_base64(plt)

def create_plot_selected(optimizer, x, y):
    plt.figure(figsize=(8, 5))

    if optimizer.productivity is not None and optimizer.current_consumption is not None:
        plt.scatter(optimizer.productivity, optimizer.current_consumption,
                   c='gray', s=5, alpha=0.5)

    if optimizer.pareto_front is not None and len(optimizer.pareto_front) > 0:
        pf_prod = optimizer.pareto_front[:, 0]
        pf_current = optimizer.pareto_front[:, 1]
        order = np.argsort(pf_prod)
        plt.plot(pf_prod[order], pf_current[order], 'r--', alpha=0.8, linewidth=1.5)
        if optimizer.optimal_point is not None:
            plt.scatter(optimizer.optimal_point[0], optimizer.optimal_point[1],
                       c='blue', s=100, label='Оптимальное')

    plt.scatter(x, y, c='cyan', s=100, marker='s', label='Выбранное')
    if optimizer.optimal_point is not None:
        plt.plot([x, optimizer.optimal_point[0]],
                [y, optimizer.optimal_point[1]],
                'c-', alpha=0.5, linewidth=2)

    plt.xlabel('Производительность', fontsize=10)
    plt.ylabel('Потребление тока (А)', fontsize=10)
    plt.grid(True, linestyle=':', alpha=0.3)
    plt.legend()
    plt.tight_layout()

    return plot_to_base64(plt)

def plot_to_base64(plt):
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=100)
    plt.close()
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{image_base64}"
