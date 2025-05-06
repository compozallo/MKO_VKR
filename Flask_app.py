from flask import Flask, render_template_string, request, jsonify
from werkzeug.serving import run_simple
import socket
from MKO_opt import ParetoOptimizer
import numpy as np
from io import BytesIO
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime

app = Flask(__name__)
optimizer = ParetoOptimizer()

# Значения по умолчанию
default_values = {
    'Давление на выходе (атм) ↑': 18,
    'Износ оборудования (%) ↓ [0-100]': 25,
    'Затраты на ТО (руб/ч) ↓': 600,
    'Возраст оборудования (лет) ↓': 7,
    'Общая эффективность ↑': 80,
    'Требуемая производительность (т/ч) ↑': 0
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

        for pump_name in optimizer.pumps:
            for param_name in optimizer.pumps[pump_name]:
                if param_name == 'Включен':
                    continue
                try:
                    optimizer.pumps[pump_name][param_name] = float(
                        request.form.get(f"{pump_name}_{param_name}", optimizer.pumps[pump_name][param_name]))
                except:
                    pass

        for pump_name in optimizer.pumps:
            optimizer.pumps[pump_name]['Включен'] = request.form.get(f"{pump_name}_enabled") == "on"

        if 'set_forecast' in request.form:
            try:
                forecast_value = float(request.form.get('forecast_value', 0))
                optimizer.set_required_productivity(forecast_value)
                input_values['Требуемая производительность (т/ч) ↑'] = forecast_value
            except:
                pass

        try:
            num_solutions = int(request.form.get('num_solutions', 1000))
        except:
            num_solutions = 1000

        optimizer.generate_solutions(num_solutions, input_values)

        fig1 = create_plot_all(optimizer)
        fig2 = create_plot_pareto(optimizer)

        general_recommendations = optimizer.get_general_recommendations()
        forecast_recommendations = optimizer.get_forecast_recommendations() if optimizer.required_productivity else []

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

        forecast_table = optimizer.get_forecast_table()

        return render_template_string(get_html_template(),
                                   plot1=fig1,
                                   plot2=fig2,
                                   general_recommendations=general_recommendations,
                                   forecast_recommendations=forecast_recommendations,
                                   criteria_names=optimizer.criteria_names,
                                   default_values=default_values,
                                   pumps=optimizer.pumps,
                                   num_solutions=num_solutions,
                                   optimal_point=optimal_point_list,
                                   local_ip=get_local_ip(),
                                   prod_min=prod_min,
                                   prod_max=prod_max,
                                   eff_min=eff_min,
                                   eff_max=eff_max,
                                   forecast_table=forecast_table,
                                   required_productivity=optimizer.required_productivity)

    forecast_table = optimizer.get_forecast_table()
    return render_template_string(get_html_template(),
                               plot1=None,
                               plot2=None,
                               general_recommendations=None,
                               forecast_recommendations=None,
                               criteria_names=optimizer.criteria_names,
                               default_values=default_values,
                               pumps=optimizer.pumps,
                               num_solutions=1000,
                               optimal_point=None,
                               local_ip=get_local_ip(),
                               prod_min=0,
                               prod_max=1,
                               eff_min=0,
                               eff_max=1,
                               forecast_table=forecast_table,
                               required_productivity=None)

@app.route('/toggle_pump', methods=['POST'])
def toggle_pump():
    try:
        pump_name = request.json['pump_name']
        state = request.json['state']
        optimizer.toggle_pump(pump_name, state)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/set_required_productivity', methods=['POST'])
def set_required_productivity():
    try:
        value = float(request.json['value'])
        optimizer.set_required_productivity(value)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

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

    recommendations = optimizer.get_general_recommendations(solution_idx)
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
        .pump-control { display: flex; align-items: center; margin-bottom: 10px; }
        .pump-switch { position: relative; display: inline-block; width: 60px; height: 34px; margin-right: 10px; }
        .pump-switch input { opacity: 0; width: 0; height: 0; }
        .pump-slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #ccc; transition: .4s; border-radius: 34px; }
        .pump-slider:before { position: absolute; content: ""; height: 26px; width: 26px; left: 4px; bottom: 4px; background-color: white; transition: .4s; border-radius: 50%; }
        input:checked + .pump-slider { background-color: #4CAF50; }
        input:checked + .pump-slider:before { transform: translateX(26px); }
        .pump-status { font-weight: bold; }
        .pump-status.on { color: #4CAF50; }
        .pump-status.off { color: #f44336; }
        .forecast-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #eee; }
        .forecast-item:last-child { border-bottom: none; }
        .add-forecast-btn { background-color: #2196F3; padding: 5px 10px; font-size: 0.9em; }
        .selected-forecast { background-color: #e7f3fe; }
        .required-productivity-box { background: #e8f5e9; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
        .recommendations-box { background: #fff3cd; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
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
                <h3>Прогнозируемые значения (т/ч)</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Время</th>
                            <th>Значение</th>
                            <th>Действие</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for forecast in forecast_table %}
                        <tr>
                            <td>{{ forecast['timestamp'] }}</td>
                            <td>{{ "%.2f"|format(forecast['val']) }}</td>
                            <td>
                                <button class="add-forecast-btn" onclick="setRequiredProductivity({{ forecast['val'] }})">
                                    Добавить
                                </button>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>

            <div class="required-productivity-box">
                <h3>Требуемая производительность</h3>
                <form method="post">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <input type="number" step="0.1" name="forecast_value"
                               value="{{ "%.2f"|format(required_productivity) if required_productivity else '' }}"
                               placeholder="Введите значение" style="flex-grow: 1;">
                        <button type="submit" name="set_forecast">Установить</button>
                    </div>
                </form>
                {% if required_productivity %}
                <p>Установлено: <strong>{{ "%.2f"|format(required_productivity) }} т/ч</strong></p>
                {% endif %}
            </div>

            <div class="tab">
                <button class="tablinks active" onclick="openTab(event, 'mainParams')">Основные</button>
                <button class="tablinks" onclick="openTab(event, 'pumpParams')">Насосы</button>
            </div>

            <div id="mainParams" class="tabcontent" style="display: block;">
                <h2>Параметры системы</h2>
                <form method="post">
                    <table>
                        {% for name in criteria_names if name != 'Требуемая производительность (т/ч) ↑' %}
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
                <h2>Управление насосами</h2>
                <form method="post">
                    {% for pump_name, pump in pumps.items() %}
                    <div class="pump-control">
                        <label class="pump-switch">
                            <input type="checkbox" name="{{ pump_name }}_enabled" {% if pump['Включен'] %}checked{% endif %} onchange="togglePump('{{ pump_name }}', this.checked)">
                            <span class="pump-slider"></span>
                        </label>
                        <span class="pump-status {% if pump['Включен'] %}on{% else %}off{% endif %}">
                            {{ pump['Название'] }}: {% if pump['Включен'] %}ВКЛ{% else %}ВЫКЛ{% endif %}
                        </span>
                    </div>
                    <table>
                        {% for param_name, param_value in pump.items() if param_name != 'Включен' and param_name != 'Название' %}
                        <tr>
                            <td>{{ param_name }}</td>
                            <td><input type="number" step="0.1" name="{{ pump_name }}_{{ param_name }}" value="{{ param_value }}" required></td>
                        </tr>
                        {% endfor %}
                    </table>
                    <br>
                    {% endfor %}
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

            {% if forecast_recommendations %}
            <div class="recommendations-box">
                <h3>Рекомендации для требуемой производительности</h3>
                <ul>
                    {% for rec in forecast_recommendations %}
                    <li>{{ rec }}</li>
                    {% endfor %}
                </ul>
            </div>
            {% endif %}

            {% if general_recommendations %}
            <div class="recommendations-box">
                <h3>Общие рекомендации по оптимизации</h3>
                <ul>
                    {% for rec in general_recommendations %}
                    <li>{{ rec }}</li>
                    {% endfor %}
                </ul>
            </div>
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

        function togglePump(pumpName, state) {
            fetch('/toggle_pump', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ pump_name: pumpName, state: state })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    alert(data.error);
                    return;
                }
                const statusElements = document.querySelectorAll(`.pump-status`);
                statusElements.forEach(el => {
                    if (el.textContent.includes(pumpName)) {
                        el.textContent = `${pumpName}: ${state ? 'ВКЛ' : 'ВЫКЛ'}`;
                        el.classList.toggle('on', state);
                        el.classList.toggle('off', !state);
                    }
                });
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Произошла ошибка при переключении насоса');
            });
        }

        function setRequiredProductivity(value) {
            fetch('/set_required_productivity', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ value: value })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    alert(data.error);
                    return;
                }
                document.querySelector('input[name="forecast_value"]').value = value;
                window.location.reload();
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Произошла ошибка при установке требуемой производительности');
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
