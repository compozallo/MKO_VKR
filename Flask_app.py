
from flask import Flask, render_template_string, request, jsonify
from werkzeug.serving import run_simple
import socket
from MKO_opt import ParetoOptimizer
import numpy as np
from io import BytesIO
import base64
import matplotlib.pyplot as plt

app = Flask(__name__)
optimizer = ParetoOptimizer()

# Обновлённые значения по умолчанию (без КПД и Производительности)
default_values = {
    'Мощность насосов (кВт) ↑': 55,
    'Давление на выходе (атм) ↑': 16,
    'Износ оборудования (%) ↓ [0-100]': 20,
    'Затраты на ТО (руб/ч) ↓': 500,
    'Возраст оборудования (лет) ↓': 5,
    'Общая эффективность ↑': 75
}

def create_plot_all(optimizer):
    plt.figure(figsize=(10, 6))

    if optimizer.objectives is not None:
        plt.scatter(optimizer.objectives[:, 0], optimizer.objectives[:, 1],
                   c=optimizer.objectives[:, 2], cmap='viridis', s=10, alpha=0.6)
        plt.colorbar(label='Общая эффективность')

    if optimizer.pareto_front is not None and len(optimizer.pareto_front) > 0:
        pf_prod = optimizer.pareto_front[:, 0]
        pf_eff = optimizer.pareto_front[:, 1]
        order = np.argsort(pf_prod)
        plt.plot(pf_prod[order], pf_eff[order], 'r--', alpha=0.8, linewidth=2, label='Парето-фронт')

        if optimizer.optimal_point is not None:
            plt.scatter(optimizer.optimal_point[0], optimizer.optimal_point[1],
                       c='red', s=150, marker='*', label='Оптимальное решение')

    plt.xlabel('Производительность (т/ч) [расчетная]', fontsize=12)
    plt.ylabel('КПД системы (%) [расчетный]', fontsize=12)
    plt.title('Пространство решений', fontsize=14)
    plt.grid(True, linestyle=':', alpha=0.5)
    plt.legend()
    plt.tight_layout()

    return plot_to_base64(plt)

def create_plot_pareto(optimizer):
    plt.figure(figsize=(10, 6))

    if optimizer.pareto_front is not None and len(optimizer.pareto_front) > 0:
        pf_prod = optimizer.pareto_front[:, 0]
        pf_eff = optimizer.pareto_front[:, 1]
        pf_overall = optimizer.pareto_front[:, 2]
        order = np.argsort(pf_prod)

        scatter = plt.scatter(pf_prod[order], pf_eff[order],
                            c=pf_overall[order], cmap='viridis', s=50)
        plt.colorbar(scatter, label='Общая эффективность')

        plt.plot(pf_prod[order], pf_eff[order], 'r--', alpha=0.5, linewidth=2)

        if optimizer.optimal_point is not None:
            plt.scatter(optimizer.optimal_point[0], optimizer.optimal_point[1],
                       c='red', s=200, marker='*', label='Оптимальное решение')

    plt.xlabel('Производительность (т/ч) [расчетная]', fontsize=12)
    plt.ylabel('КПД системы (%) [расчетный]', fontsize=12)
    plt.title('Парето-фронт оптимальных решений', fontsize=14)
    plt.grid(True, linestyle=':', alpha=0.5)
    plt.legend()
    plt.tight_layout()

    return plot_to_base64(plt)

def create_plot_selected(optimizer, x, y):
    plt.figure(figsize=(10, 6))

    if optimizer.objectives is not None:
        plt.scatter(optimizer.objectives[:, 0], optimizer.objectives[:, 1],
                   c=optimizer.objectives[:, 2], cmap='viridis', s=10, alpha=0.3)

    if optimizer.pareto_front is not None and len(optimizer.pareto_front) > 0:
        pf_prod = optimizer.pareto_front[:, 0]
        pf_eff = optimizer.pareto_front[:, 1]
        order = np.argsort(pf_prod)
        plt.plot(pf_prod[order], pf_eff[order], 'r--', alpha=0.5, linewidth=2)

        if optimizer.optimal_point is not None:
            plt.scatter(optimizer.optimal_point[0], optimizer.optimal_point[1],
                       c='red', s=150, marker='*', label='Оптимальное')

    plt.scatter(x, y, c='blue', s=150, marker='o', label='Выбранное')

    if optimizer.optimal_point is not None:
        plt.plot([x, optimizer.optimal_point[0]],
                [y, optimizer.optimal_point[1]],
                'b-', alpha=0.3, linewidth=2)

    plt.xlabel('Производительность (т/ч) [расчетная]', fontsize=12)
    plt.ylabel('КПД системы (%) [расчетный]', fontsize=12)
    plt.title('Сравнение решений', fontsize=14)
    plt.grid(True, linestyle=':', alpha=0.5)
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
                input_values[name] = float(request.form.get(name, default_values.get(name, 0)))
            except:
                pass

        for name in optimizer.pump_params:
            try:
                optimizer.pump_params[name] = float(request.form.get(f"pump_{name}", optimizer.pump_params[name]))
            except:
                pass

        try:
            num_solutions = int(request.form.get('num_solutions', 1000))
        except:
            num_solutions = 1000

        optimizer.generate_solutions(num_solutions, input_values)

        fig1 = create_plot_all(optimizer)
        fig2 = create_plot_pareto(optimizer)
        recommendations = optimizer.get_recommendations()

        optimal_point_list = None
        if optimizer.optimal_point is not None:
            optimal_point_list = optimizer.optimal_point.tolist()

        if optimizer.objectives is not None:
            prod_min = float(np.min(optimizer.objectives[:, 0]))
            prod_max = float(np.max(optimizer.objectives[:, 0]))
            eff_min = float(np.min(optimizer.objectives[:, 1]))
            eff_max = float(np.max(optimizer.objectives[:, 1]))
        else:
            prod_min, prod_max, eff_min, eff_max = 0, 1, 0, 1

        return render_template_string(get_html_template(),
                                   plot1=fig1,
                                   plot2=fig2,
                                   recommendations=recommendations,
                                   criteria_names=optimizer.criteria_names,
                                   default_values=default_values,
                                   pump_params=optimizer.pump_params,
                                   num_solutions=num_solutions,
                                   optimal_point=optimal_point_list,
                                   local_ip=get_local_ip(),
                                   prod_min=prod_min,
                                   prod_max=prod_max,
                                   eff_min=eff_min,
                                   eff_max=eff_max,
                                   last_forecast=optimizer.last_forecast_value)

    return render_template_string(get_html_template(),
                               plot1=None,
                               plot2=None,
                               recommendations=None,
                               criteria_names=optimizer.criteria_names,
                               default_values=default_values,
                               pump_params=optimizer.pump_params,
                               num_solutions=1000,
                               optimal_point=None,
                               local_ip=get_local_ip(),
                               prod_min=0,
                               prod_max=1,
                               eff_min=0,
                               eff_max=1,
                               last_forecast=optimizer.last_forecast_value)

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

    fig = create_plot_selected(optimizer, x, y)

    return jsonify({
        'recommendations': recommendations,
        'plot': fig,
        'selected_point': [x, y],
        'solution_values': solution_values
    })

def get_html_template():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Оптимизация БКНС</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { display: flex; flex-wrap: wrap; gap: 20px; }
        .panel { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .params { flex: 1; min-width: 300px; }
        .results { flex: 2; min-width: 600px; }
        .plot-container { margin-bottom: 30px; }
        .plot { width: 100%; height: 400px; object-fit: contain; cursor: crosshair; border: 1px solid #ddd; border-radius: 4px; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f0f0f0; }
        input[type="number"] { width: 100px; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        button { background-color: #4CAF50; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; }
        button:hover { background-color: #45a049; }
        .recommendations { background: #f8f9fa; padding: 15px; border-radius: 8px; margin-top: 20px; }
        .solution-values { background: #e9f7ef; padding: 15px; border-radius: 8px; margin-top: 20px; }
        .info-box { background: #e7f3fe; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
        .forecast-box { background: #fff3cd; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
        .pump-params { background: #e2e3e5; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
        h1 { color: #333; }
        h2 { color: #444; margin-top: 0; }
        h3 { color: #555; }
        .tab { overflow: hidden; border: 1px solid #ccc; background-color: #f1f1f1; border-radius: 4px 4px 0 0; }
        .tab button { background-color: inherit; float: left; border: none; outline: none; cursor: pointer; padding: 10px 16px; transition: 0.3s; color: black; }
        .tab button:hover { background-color: #ddd; }
        .tab button.active { background-color: #ccc; }
        .tabcontent { display: none; padding: 15px; border: 1px solid #ccc; border-top: none; border-radius: 0 0 4px 4px; background: white; }
    </style>
</head>
<body>
    <div class="container">
        <div class="panel params">
            <h1>Оптимизация БКНС</h1>

            <div class="info-box">
                <p>Для доступа с других устройств: <strong>http://{{ local_ip }}:1500</strong></p>
            </div>

            <div class="forecast-box">
                <h3>Прогнозируемое значение</h3>
                <p>Последнее значение из CSV: <strong>{{ "%.2f"|format(last_forecast) }}</strong></p>
            </div>

            <div class="tab">
                <button class="tablinks active" onclick="openTab(event, 'mainParams')">Основные</button>
                <button class="tablinks" onclick="openTab(event, 'pumpParams')">Насос</button>
            </div>

            <div id="mainParams" class="tabcontent" style="display: block;">
                <h2>Параметры системы</h2>
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
                            <td><input type="number" name="num_solutions" min="100" max="10000" value="{{ num_solutions }}" required></td>
                        </tr>
                    </table>
                    <br>
                    <button type="submit">Рассчитать оптимизацию</button>
                </form>
            </div>

            <div id="pumpParams" class="tabcontent">
                <h2>Параметры насоса</h2>
                <form method="post">
                    <table>
                        {% for name, value in pump_params.items() %}
                        <tr>
                            <td>{{ name }}</td>
                            <td><input type="number" step="0.1" name="pump_{{ name }}" value="{{ value }}" required></td>
                        </tr>
                        {% endfor %}
                    </table>
                    <br>
                    <button type="submit">Обновить параметры</button>
                </form>
            </div>

            {% if optimal_point %}
            <div class="solution-values">
                <h2>Оптимальное решение</h2>
                <p><strong>Производительность:</strong> {{ "%.2f"|format(optimal_point[0]) }} т/ч (расчетная)</p>
                <p><strong>КПД системы:</strong> {{ "%.2f"|format(optimal_point[1]) }}% (расчетный)</p>
                <p><strong>Общая эффективность:</strong> {{ "%.2f"|format(optimal_point[2]) }}%</p>
            </div>
            {% endif %}
        </div>

        <div class="panel results">
            {% if plot1 and plot2 %}
            <div class="plot-container">
                <h2>Пространство решений</h2>
                <p>Кликните на точку для анализа конкретного решения</p>
                <img id="main-plot" src="{{ plot1 }}" class="plot" onclick="handlePlotClick(event, this)">
            </div>

            <div class="plot-container">
                <h2>Парето-фронт оптимальных решений</h2>
                <img src="{{ plot2 }}" class="plot">
            </div>

            <div id="selected-info" style="display: none;">
                <div class="solution-values" id="solution-values"></div>
                <div class="recommendations" id="recommendations"></div>
                <div class="plot-container">
                    <h3>Сравнение с оптимальным решением</h3>
                    <img id="selected-plot" src="" class="plot">
                </div>
            </div>
            {% else %}
            <h2>Результаты оптимизации</h2>
            <p>Введите параметры системы и нажмите "Рассчитать оптимизацию"</p>
            {% endif %}
        </div>
    </div>

    <script>
        function openTab(evt, tabName) {
            var i, tabcontent, tablinks;
            tabcontent = document.getElementsByClassName("tabcontent");
            for (i = 0; i < tabcontent.length; i++) {
                tabcontent[i].style.display = "none";
            }
            tablinks = document.getElementsByClassName("tablinks");
            for (i = 0; i < tablinks.length; i++) {
                tablinks[i].className = tablinks[i].className.replace(" active", "");
            }
            document.getElementById(tabName).style.display = "block";
            evt.currentTarget.className += " active";
        }

        function handlePlotClick(event, element) {
            const rect = element.getBoundingClientRect();
            const x = event.clientX - rect.left;
            const y = event.clientY - rect.top;

            const normX = x / rect.width;
            const normY = 1 - (y / rect.height);

            const dataX = {{ prod_min }} + normX * ({{ prod_max }} - {{ prod_min }});
            const dataY = {{ eff_min }} + normY * ({{ eff_max }} - {{ eff_min }});

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

                document.getElementById('selected-info').style.display = 'block';
                document.getElementById('selected-plot').src = data.plot;

                let valuesHtml = '<h2>Параметры выбранного решения</h2><table>';
                for (const [name, value] of Object.entries(data.solution_values)) {
                    valuesHtml += `<tr><td>${name}</td><td>${value.toFixed(2)}</td></tr>`;
                }
                
                // Добавляем расчетные параметры
                const productivity = {{ prod_min }} + (x - {{ prod_min }}) / ({{ prod_max }} - {{ prod_min }}) * ({{ prod_max }} - {{ prod_min }});
                const efficiency = {{ eff_min }} + (y - {{ eff_min }}) / ({{ eff_max }} - {{ eff_min }}) * ({{ eff_max }} - {{ eff_min }});
                
                valuesHtml += `<tr><td>Производительность (расчетная)</td><td>${productivity.toFixed(2)} т/ч</td></tr>`;
                valuesHtml += `<tr><td>КПД системы (расчетный)</td><td>${efficiency.toFixed(2)}%</td></tr>`;
                valuesHtml += '</table>';
                document.getElementById('solution-values').innerHTML = valuesHtml;

                let recHtml = '<h2>Рекомендации по улучшению</h2><ul>';
                data.recommendations.forEach(rec => {
                    recHtml += `<li>${rec}</li>`;
                });
                recHtml += '</ul>';
                document.getElementById('recommendations').innerHTML = recHtml;

                document.getElementById('selected-info').scrollIntoView({ behavior: 'smooth' });
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Произошла ошибка при обработке запроса');
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