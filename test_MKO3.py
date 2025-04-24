import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask, render_template_string, request, jsonify
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from io import BytesIO
import base64
import random
from werkzeug.serving import run_simple
import socket

app = Flask(__name__)

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

# Создаем экземпляр оптимизатора
optimizer = ParetoOptimizer()

default_values = {
    'Мощность насосов (кВт) ↑': 110,
    'Давление на выходе (атм) ↑': 25,
    'Потребление тока (А) ↓': 185,
    'Энергопотребление (кВт·ч) ↓': 95,
    'Износ оборудования (%) ↓ [0-100]': 25,
    'Температура двигателя (°C) ↓ [0-120]': 75,
    'Квалификация рабочих (баллы) ↑ [0-10]': 6,
    'КПД насоса (%) ↑ [0-100]': 68,
    'Затраты на ТО (руб/ч) ↓': 350,
    'Возраст оборудования (лет) ↓': 5
}

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        input_values = default_values.copy()
        for name in optimizer.criteria_names:
            try:
                input_values[name] = float(request.form.get(name, default_values[name]))
            except:
                pass
        
        try:
            num_solutions = int(request.form.get('num_solutions', 1000))
        except:
            num_solutions = 1000
        
        optimizer.generate_solutions(num_solutions, input_values)
        
        fig1 = create_plot_all()
        fig2 = create_plot_pareto()
        
        recommendations = optimizer.get_recommendations()
        
        optimal_point_list = None
        if optimizer.optimal_point is not None:
            optimal_point_list = optimizer.optimal_point.tolist()
        
        # Получаем min/max для осей графика
        prod_min = float(np.min(optimizer.productivity)) if optimizer.productivity is not None else 0
        prod_max = float(np.max(optimizer.productivity)) if optimizer.productivity is not None else 1
        curr_min = float(np.min(optimizer.current_consumption)) if optimizer.current_consumption is not None else 0
        curr_max = float(np.max(optimizer.current_consumption)) if optimizer.current_consumption is not None else 1
        
        return render_template_string(get_html_template(), 
                                   plot1=fig1,
                                   plot2=fig2,
                                   recommendations=recommendations,
                                   criteria_names=optimizer.criteria_names,
                                   default_values=default_values,
                                   num_solutions=num_solutions,
                                   optimal_point=optimal_point_list,
                                   local_ip=get_local_ip(),
                                   prod_min=prod_min,
                                   prod_max=prod_max,
                                   curr_min=curr_min,
                                   curr_max=curr_max)
    
    # Для GET-запроса передаем только необходимые данные
    return render_template_string(get_html_template(), 
                               plot1=None,
                               plot2=None,
                               recommendations=None,
                               criteria_names=optimizer.criteria_names,
                               default_values=default_values,
                               num_solutions=1000,
                               optimal_point=None,
                               local_ip=get_local_ip(),
                               prod_min=0,
                               prod_max=1,
                               curr_min=0,
                               curr_max=1)

@app.route('/select_point', methods=['POST'])
def select_point():
    try:
        x = float(request.json['x'])
        y = float(request.json['y'])
    except:
        return jsonify({'error': 'Invalid coordinates'}), 400
    
    solution_idx = optimizer.find_closest_solution(x, y)
    if solution_idx is None:
        return jsonify({'error': 'No solutions available'}), 400
    
    recommendations = optimizer.get_recommendations(solution_idx)
    solution_values = {name: float(optimizer.solutions[solution_idx, i]) 
                      for i, name in enumerate(optimizer.criteria_names)}
    
    fig = create_plot_selected(x, y)
    
    return jsonify({
        'recommendations': recommendations,
        'plot': fig,
        'selected_point': [x, y],
        'solution_values': solution_values
    })

def create_plot_all():
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

def create_plot_pareto():
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

def create_plot_selected(x, y):
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

def get_html_template():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Оптимизация насосной станции</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .container { display: flex; flex-wrap: wrap; }
        .params { flex: 1; min-width: 300px; padding: 10px; }
        .results { flex: 2; min-width: 500px; padding: 10px; }
        .plot { width: 100%; margin-bottom: 20px; cursor: crosshair; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }
        input[type="number"] { width: 80px; }
        .recommendations { background: #f5f5f5; padding: 10px; border-radius: 5px; }
        .solution-values { background: #f0f8ff; padding: 10px; border-radius: 5px; margin-top: 10px; }
        .info-box { margin-top: 20px; padding: 10px; background: #e6e6fa; border-radius: 5px; }
    </style>
</head>
<body>
    <h1>Оптимизация параметров насосной станции</h1>
    
    <div class="info-box">
        <p>Для доступа с других устройств в локальной сети используйте: <strong>http://{{ local_ip }}:1500</strong></p>
    </div>
    
    <div class="container">
        <div class="params">
            <h2>Параметры станции</h2>
            <form method="post">
                <table>
                    {% for name in criteria_names %}
                    <tr>
                        <td>{{ name }}</td>
                        <td><input type="number" step="0.1" name="{{ name }}" value="{{ default_values[name] }}" required></td>
                    </tr>
                    {% endfor %}
                    <tr>
                        <td>Количество решений:</td>
                        <td><input type="number" name="num_solutions" min="100" max="5000" value="{{ num_solutions }}" required></td>
                    </tr>
                </table>
                <br>
                <input type="submit" value="Рассчитать">
            </form>
            
            {% if optimal_point %}
            <h2>Оптимальные показатели</h2>
            <p>Производительность: {{ "%.2f"|format(optimal_point[0]) }}</p>
            <p>Потребление тока: {{ "%.2f"|format(optimal_point[1]) }} А</p>
            {% endif %}
        </div>
        
        <div class="results">
            {% if plot1 and plot2 %}
            <h2>Результаты оптимизации</h2>
            
            <h3>Все решения (кликните на точку для анализа)</h3>
            <img id="main-plot" src="{{ plot1 }}" class="plot" onclick="handlePlotClick(event, this)">
            
            <h3>Парето-фронт</h3>
            <img src="{{ plot2 }}" class="plot">
            
            <div id="selected-info" style="display: none;">
                <h3>Выбранное решение</h3>
                <div class="solution-values" id="solution-values"></div>
                
                <h3>Рекомендации</h3>
                <div class="recommendations" id="recommendations"></div>
                
                <img id="selected-plot" src="" class="plot">
            </div>
            {% endif %}
        </div>
    </div>
    
    <script>
        function handlePlotClick(event, element) {
            const rect = element.getBoundingClientRect();
            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;
            
            // Нормализуем координаты (0-1)
            const normX = x / rect.width;
            const normY = 1 - (y / rect.height);  // Инвертируем Y
            
            // Преобразуем в координаты данных
            const dataX = {{ prod_min }} + normX * ({{ prod_max }} - {{ prod_min }});
            const dataY = {{ curr_min }} + normY * ({{ curr_max }} - {{ curr_min }});
            
            selectPoint(dataX, dataY);
        }
        
        function selectPoint(x, y) {
            fetch('/select_point', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ x: x, y: y })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    alert(data.error);
                    return;
                }
                
                // Показываем блок с информацией
                document.getElementById('selected-info').style.display = 'block';
                
                // Обновляем график
                document.getElementById('selected-plot').src = data.plot;
                
                // Форматируем значения параметров
                let valuesHtml = '<table>';
                for (const [name, value] of Object.entries(data.solution_values)) {
                    valuesHtml += `<tr><td>${name}</td><td>${value.toFixed(2)}</td></tr>`;
                }
                valuesHtml += '</table>';
                document.getElementById('solution-values').innerHTML = valuesHtml;
                
                // Обновляем рекомендации
                const recList = data.recommendations.map(rec => `<li>${rec}</li>`).join('');
                document.getElementById('recommendations').innerHTML = `<ul>${recList}</ul>`;
                
                // Прокручиваем к выбранному решению
                document.getElementById('selected-info').scrollIntoView({ behavior: 'smooth' });
            });
        }
    </script>
</body>
</html>
    """

if __name__ == '__main__':
    local_ip = get_local_ip()
    print(f"Запуск сервера. Доступно по адресам:")
    print(f"Локально: http://127.0.0.1:1500")
    print(f"В локальной сети: http://{local_ip}:1500")
    
    run_simple(local_ip, 1500, app, use_reloader=True, use_debugger=True)