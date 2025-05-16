from flask import Flask, render_template, request, jsonify
import socket
import numpy as np
from MKO_opt import ParetoOptimizer
import plotly.graph_objects as go

app = Flask(__name__)
optimizer = ParetoOptimizer()
selected_point = None

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

def create_main_plot_json():
    global selected_point
    fig = go.Figure()

    if optimizer.objectives is not None and len(optimizer.objectives) > 0:
        fig.add_trace(go.Scatter(
            x=optimizer.objectives[:, 0],
            y=optimizer.objectives[:, 1],
            mode='markers',
            marker=dict(
                color=optimizer.objectives[:, 2],
                colorscale='Viridis',
                size=8,
                opacity=0.5,
                colorbar=dict(title='Общая эффективность')
            ),
            name='Все решения',
            customdata=np.arange(len(optimizer.objectives)).tolist(),
            hoverinfo='text',
            hovertext=[f'П: {x:.2f} т/ч<br>КПД: {y:.2f}%' for x, y in zip(optimizer.objectives[:, 0], optimizer.objectives[:, 1])]
        ))

        if selected_point:
            fig.add_trace(go.Scatter(
                x=[selected_point[0]],
                y=[selected_point[1]],
                mode='markers+text',
                marker=dict(size=14, color='red', symbol='circle'),
                name='Целевая точка',
                text=["Перетащить"],
                textposition="top center"
            ))

        if optimizer.pareto_front is not None and len(optimizer.pareto_front) > 0:
            pf = optimizer.pareto_front
            order = np.argsort(pf[:, 0])
            fig.add_trace(go.Scatter(
                x=pf[order, 0],
                y=pf[order, 1],
                mode='lines+markers',
                line=dict(color='orange', width=3),
                marker=dict(size=10, color='orange'),
                name='Парето-фронт',
                customdata=order.tolist(),
                hoverinfo='text',
                hovertext=[f'Парето: {x:.2f}, {y:.2f}' for x, y in zip(pf[order, 0], pf[order, 1])]
            ))

        # Добавляем звёздочку оптимума
        if optimizer.optimal_point is not None:
            fig.add_trace(go.Scatter(
                x=[optimizer.optimal_point[0]],
                y=[optimizer.optimal_point[1]],
                mode='markers',
                marker=dict(size=18, color='gold', symbol='star'),
                name='Оптимум'
            ))

    fig.update_layout(
        title='Парето-фронт и решения',
        xaxis_title='Производительность (т/ч)',
        yaxis_title='КПД (%)',
        dragmode='select',
        clickmode='event+select',
        height=600
    )
    return fig.to_dict()

def create_path_plot_json():
    global selected_point
    fig = go.Figure()

    if optimizer.objectives is not None and len(optimizer.objectives) > 0:
        fig.add_trace(go.Scatter(
            x=optimizer.objectives[:, 0],
            y=optimizer.objectives[:, 1],
            mode='markers',
            marker=dict(color=optimizer.objectives[:, 2], colorscale='Viridis', size=8, opacity=0.3),
            name='Все решения',
            hoverinfo='skip'
        ))

        if optimizer.pareto_front is not None and len(optimizer.pareto_front) > 0:
            pf = optimizer.pareto_front
            order = np.argsort(pf[:, 0])
            fig.add_trace(go.Scatter(
                x=pf[order, 0],
                y=pf[order, 1],
                mode='lines+markers',
                line=dict(color='orange', width=3),
                marker=dict(size=10, color='orange'),
                name='Парето-фронт'
            ))

    target_point = selected_point
    if target_point is None and optimizer.optimal_point is not None:
        target_point = optimizer.optimal_point[:2]

    if target_point is not None:
        idx = optimizer.find_closest_solution(target_point[0], target_point[1])
        if idx is not None:
            path = optimizer.get_path_to_solution(idx)
            if path:
                x_vals, y_vals = zip(*path)
                fig.add_trace(go.Scatter(
                    x=x_vals, y=y_vals,
                    mode='lines+markers',
                    line=dict(color='purple', width=4),
                    marker=dict(size=8),
                    name='Путь к решению'
                ))
                fig.add_trace(go.Scatter(
                    x=[x_vals[0]], y=[y_vals[0]],
                    mode='markers',
                    marker=dict(size=14, color='red'),
                    name='Текущее состояние'
                ))
                fig.add_trace(go.Scatter(
                    x=[x_vals[-1]], y=[y_vals[-1]],
                    mode='markers',
                    marker=dict(size=16, color='blue', symbol='star'),
                    name='Цель'
                ))

    fig.update_layout(
        title='Путь к цели',
        xaxis_title='Производительность (т/ч)',
        yaxis_title='КПД (%)',
        height=600
    )
    return fig.to_dict()

@app.route('/move_point', methods=['POST'])
def move_point():
    global selected_point
    data = request.get_json()
    x = float(data['x'])
    y = float(data['y'])
    selected_point = (x, y)

    idx = optimizer.find_closest_solution(x, y)
    main_plot = create_main_plot_json()
    path_plot = create_path_plot_json()
    radar_chart = optimizer.create_radar_chart_json()
    detailed = optimizer.get_detailed_recommendations(idx)
    general = optimizer.get_general_recommendations(idx)
    return jsonify({
        'main_plot': main_plot,
        'path_plot': path_plot,
        'radar_chart': radar_chart,
        'detailed': detailed,
        'general': general
    })

@app.route('/', methods=['GET', 'POST'])
def index():
    global selected_point
    default_values = {
        'Давление на выходе (атм) ↑': 10,
        'Износ оборудования (%) ↓ [0-100]': 30,
        'Затраты на ТО (руб/ч) ↓': 500,
        'Возраст оборудования (лет) ↓': 5,
        'Общая эффективность ↑': 70,
        'Требуемая производительность (т/ч) ↑': 50
    }
    num_solutions = 500

    if request.method == 'POST':
        form = request.form
        inputs = {k: float(form.get(k, default_values[k])) for k in default_values}
        num_solutions = int(form.get('num_solutions', 500))
        for name in optimizer.pumps:
            optimizer.toggle_pump(name, form.get(f"{name}_enabled") == 'on')
            for param in optimizer.pumps[name]:
                if param not in ['Включен', 'Название']:
                    field = f"{name}_{param}"
                    if field in form:
                        optimizer.pumps[name][param] = float(form.get(field))

        optimizer.generate_solutions(num_solutions, inputs)
        optimizer.set_required_productivity(inputs['Требуемая производительность (т/ч) ↑'])
        selected_point = None

    return render_template('main_template.html',
        criteria_names=optimizer.criteria_names,
        default_values=default_values,
        num_solutions=num_solutions,
        pumps=optimizer.pumps,
        main_plot=optimizer.create_main_plot_json(),
        path_plot=optimizer.create_path_plot_json(),
        radar_chart=optimizer.create_radar_chart_json() if optimizer.current_values else None,
        general_recommendations=optimizer.get_general_recommendations() if optimizer.current_values else [],
        detailed_recommendations=[],
        forecast_recommendations=optimizer.get_forecast_recommendations() if optimizer.current_values else [],
        forecast_table=optimizer.get_forecast_table_html()
    )

if __name__ == '__main__':
    ip = get_local_ip()
    print(f"Запущено на http://{ip}:1500")
    app.run(host=ip, port=1500, debug=True)
