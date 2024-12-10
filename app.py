from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
import os
import hashlib
import db
from datetime import date

# Configuración del template folder
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

app = Flask(__name__, template_folder=template_dir)
app.secret_key = 'your_secret_key'

# Página principal: muestra la página de bienvenida con opciones para registrarse o iniciar sesión
@app.route('/')
def main():
    return render_template('main.html')

# Registro de usuarios
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Validación básica
        if not username or not email or not password:
            flash('Todos los campos son obligatorios.', 'danger')
            return redirect(url_for('register'))

        # Encriptar la contraseña
        hashed_password = hashlib.sha256(password.encode()).hexdigest()

        # Verificar si el email ya existe
        cursor = db.database.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if user:
            flash('El correo electrónico ya está registrado.', 'danger')
            return redirect(url_for('register'))

        # Insertar el nuevo usuario
        try:
            cursor.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (username, email, hashed_password)
            )
            db.database.commit()
            flash('Registro exitoso. Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Error al registrar el usuario: {str(e)}', 'danger')
            return redirect(url_for('register'))
        finally:
            cursor.close()

    return render_template('register.html')


# Inicio de sesión
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_password = hashlib.sha256(password.encode()).hexdigest()

        # Credenciales quemadas para el administrador
        admin_email = "admin@example.com"
        admin_password = hashlib.sha256("adminpassword".encode()).hexdigest()

        # Verificar si es el usuario administrador
        if email == admin_email and hashed_password == admin_password:
            session['user_id'] = 0  # ID ficticio para el administrador
            session['username'] = "Admin"
            session['is_admin'] = True  # Usado solo para lógica en sesión, no en BD
            flash('Inicio de sesión como administrador exitoso.', 'success')
            return redirect(url_for('notes'))

        # Verificar usuarios normales en la base de datos
        cursor = db.database.cursor()
        cursor.execute("SELECT id, username FROM users WHERE email = %s AND password = %s", (email, hashed_password))
        user = cursor.fetchone()
        cursor.close()

        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['is_admin'] = False
            flash('Inicio de sesión exitoso.', 'success')
            return redirect(url_for('notes'))
        else:
            flash('Credenciales incorrectas. Inténtalo de nuevo.', 'danger')
            return redirect(url_for('login'))

    return render_template('login.html')



# Cerrar sesión
@app.route('/logout')
def logout():
    session.clear()
    flash('Has cerrado sesión.', 'info')
    return redirect(url_for('main'))

# Página de notas: muestra las tareas (post-its)
@app.route('/notes')
def notes():
    if 'user_id' not in session:
        flash('Debes iniciar sesión para acceder a esta página.', 'warning')
        return redirect(url_for('login'))

    cursor = db.database.cursor()

    if session.get('is_admin', False):
        # Si el usuario es administrador, muestra todo
        cursor.execute("""
            SELECT projects.*, users.username AS creator_name
            FROM projects
            JOIN users ON projects.user_id = users.id
        """)
        projects = cursor.fetchall()
        project_list = [dict(zip([column[0] for column in cursor.description], record)) for record in projects]

        cursor.execute("""
            SELECT tasks.*, projects.name AS project_name
            FROM tasks
            LEFT JOIN projects ON tasks.project_id = projects.id
        """)
        tasks = cursor.fetchall()
        task_list = [dict(zip([column[0] for column in cursor.description], record)) for record in tasks]

        cursor.execute("""
            SELECT comments.*, tasks.title AS task_title
            FROM comments
            LEFT JOIN tasks ON comments.task_id = tasks.id
            LEFT JOIN projects ON tasks.project_id = projects.id
        """)
        comments = cursor.fetchall()
        comment_list = [dict(zip([column[0] for column in cursor.description], record)) for record in comments]
    else:
        # Si el usuario no es administrador, filtra por user_id
        user_id = session['user_id']
        cursor.execute("SELECT * FROM projects WHERE user_id = %s", (user_id,))
        projects = cursor.fetchall()
        project_list = [dict(zip([column[0] for column in cursor.description], record)) for record in projects]

        cursor.execute("""
            SELECT tasks.*, projects.name AS project_name
            FROM tasks
            LEFT JOIN projects ON tasks.project_id = projects.id
            WHERE projects.user_id = %s
        """, (user_id,))
        tasks = cursor.fetchall()
        task_list = [dict(zip([column[0] for column in cursor.description], record)) for record in tasks]

        cursor.execute("""
            SELECT comments.*, tasks.title AS task_title
            FROM comments
            LEFT JOIN tasks ON comments.task_id = tasks.id
            LEFT JOIN projects ON tasks.project_id = projects.id
            WHERE projects.user_id = %s
        """, (user_id,))
        comments = cursor.fetchall()
        comment_list = [dict(zip([column[0] for column in cursor.description], record)) for record in comments]

    cursor.close()

    return render_template(
        'notas.html',
        projects=project_list,
        tasks=task_list,
        comments=comment_list,
        current_user={'id': session['user_id'], 'username': session['username']}
    )



# Ruta para agregar o editar proyectos
from datetime import date

@app.route('/project', methods=['POST'])
def add_or_edit_project():
    project_id = request.form.get('id')  # Obtener ID del proyecto si existe
    name = request.form['name']
    description = request.form.get('description', '')
    start_date = request.form.get('start_date', date.today().isoformat())  # Fecha actual como valor por defecto
    end_date = request.form.get('end_date', date.today().isoformat())  # Fecha actual como valor por defecto
    difficulty = request.form.get('difficulty', 'Media')

    cursor = db.database.cursor()

    if project_id:  # Si hay un ID, actualizar el proyecto
        sql = """
        UPDATE projects 
        SET name = %s, description = %s, start_date = %s, end_date = %s, difficulty = %s 
        WHERE id = %s
        """
        cursor.execute(sql, (name, description, start_date, end_date, difficulty, project_id))
        flash('Proyecto actualizado correctamente.', 'success')
    else:  # Si no hay ID, crear un nuevo proyecto
        sql = """
        INSERT INTO projects (name, description, start_date, end_date, difficulty, user_id) 
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        user_id = session['user_id']
        cursor.execute(sql, (name, description, start_date, end_date, difficulty, user_id))
        flash('Proyecto creado correctamente.', 'success')

    db.database.commit()
    cursor.close()

    return redirect(url_for('notes'))




@app.route('/task', methods=['POST'])
def add_or_edit_task():
    task_id = request.form.get('id')  # Obtener ID de la tarea si existe
    title = request.form['title']
    description = request.form.get('description', '')
    project_id = request.form['project_id']
    cost = float(request.form.get('cost', 0))  # Obtener el costo, con valor predeterminado de 0 si no se proporciona

    cursor = db.database.cursor()

    if task_id:  # Si hay un ID, actualizar la tarea
        sql = """
        UPDATE tasks 
        SET title = %s, description = %s, project_id = %s, cost = %s 
        WHERE id = %s
        """
        cursor.execute(sql, (title, description, project_id, cost, task_id))
        flash('Tarea actualizada correctamente.', 'success')
    else:  # Si no hay ID, crear una nueva tarea
        sql = """
        INSERT INTO tasks (title, description, project_id, cost) 
        VALUES (%s, %s, %s, %s)
        """
        cursor.execute(sql, (title, description, project_id, cost))
        flash('Tarea creada correctamente.', 'success')

    db.database.commit()
    cursor.close()

    return redirect(url_for('notes'))




# Ruta para agregar o editar comentarios
@app.route('/comment', methods=['POST'])
def add_or_edit_comment():
    comment_id = request.form.get('id')  # Obtener ID del comentario si existe
    content = request.form['content']
    task_id = request.form['task_id']
    user_id = session['user_id']  # Usuario actual

    cursor = db.database.cursor()

    if comment_id:  # Si hay un ID, actualizar el comentario
        sql = """
        UPDATE comments 
        SET content = %s, task_id = %s 
        WHERE id = %s
        """
        cursor.execute(sql, (content, task_id, comment_id))
        flash('Comentario actualizado correctamente.', 'success')
    else:  # Si no hay ID, crear un nuevo comentario
        sql = """
        INSERT INTO comments (content, task_id, user_id) 
        VALUES (%s, %s, %s)
        """
        cursor.execute(sql, (content, task_id, user_id))
        flash('Comentario creado correctamente.', 'success')

    db.database.commit()
    cursor.close()

    return redirect(url_for('notes'))



# Ruta para eliminar proyectos
@app.route('/delete_project/<int:id>', methods=['GET'])
def delete_project(id):
    cursor = db.database.cursor()
    cursor.execute("DELETE FROM projects WHERE id = %s", (id,))
    db.database.commit()
    cursor.close()
    flash('Proyecto eliminado correctamente.', 'success')
    return redirect(url_for('edit_notes'))

# Ruta para eliminar tareas
@app.route('/delete_task/<int:id>', methods=['GET'])
def delete_task(id):
    cursor = db.database.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = %s", (id,))
    db.database.commit()
    cursor.close()
    flash('Tarea eliminada correctamente.', 'success')
    return redirect(url_for('edit_notes'))

# Ruta para eliminar comentarios
@app.route('/delete_comment/<int:id>', methods=['GET'])
def delete_comment(id):
    cursor = db.database.cursor()
    cursor.execute("DELETE FROM comments WHERE id = %s", (id,))
    db.database.commit()
    cursor.close()
    flash('Comentario eliminado correctamente.', 'success')
    return redirect(url_for('edit_notes'))

@app.route('/admin/users', methods=['GET', 'POST'])
def edit_users():
    # Verificar si el usuario tiene permisos de administrador
    if 'user_id' not in session or not session.get('is_admin', False):
        flash('Acceso denegado. Solo administradores pueden acceder a esta sección.', 'danger')
        return redirect(url_for('notes'))

    cursor = db.database.cursor()

    if request.method == 'POST':
        # Actualizar información del usuario
        user_id = request.form.get('id')
        username = request.form.get('username')
        email = request.form.get('email')

        cursor.execute(
            "UPDATE users SET username = %s, email = %s WHERE id = %s",
            (username, email, user_id)
        )
        db.database.commit()
        flash('Usuario actualizado exitosamente.', 'success')

    # Obtener lista de usuarios
    cursor.execute("SELECT id, username, email FROM users")
    users = cursor.fetchall()
    user_list = [dict(zip([column[0] for column in cursor.description], record)) for record in users]
    cursor.close()

    return render_template('edit_users.html', users=user_list)



# Ruta para mostrar la página de edición
@app.route('/edit', methods=['GET', 'POST'])
def edit_notes():
    if 'user_id' not in session:
        flash('Debes iniciar sesión para acceder a esta página.', 'warning')
        return redirect(url_for('login'))

    item_type = request.args.get('type')  # Tipo de elemento (project, task, comment)
    item_id = request.args.get('id')  # ID del elemento a editar
    cursor = db.database.cursor()

    # Obtener todos los proyectos, tareas y comentarios si es administrador
    if session.get('is_admin', False):
        cursor.execute("SELECT * FROM projects")
        projects = cursor.fetchall()
        project_list = [dict(zip([column[0] for column in cursor.description], record)) for record in projects]

        cursor.execute("""
            SELECT tasks.*, projects.name AS project_name
            FROM tasks
            LEFT JOIN projects ON tasks.project_id = projects.id
        """)
        tasks = cursor.fetchall()
        task_list = [dict(zip([column[0] for column in cursor.description], record)) for record in tasks]

        cursor.execute("""
            SELECT comments.*, tasks.title AS task_title
            FROM comments
            LEFT JOIN tasks ON comments.task_id = tasks.id
            LEFT JOIN projects ON tasks.project_id = projects.id
        """)
        comments = cursor.fetchall()
        comment_list = [dict(zip([column[0] for column in cursor.description], record)) for record in comments]
    else:
        # Filtrar por usuario logueado si no es administrador
        user_id = session['user_id']
        cursor.execute("SELECT * FROM projects WHERE user_id = %s", (user_id,))
        projects = cursor.fetchall()
        project_list = [dict(zip([column[0] for column in cursor.description], record)) for record in projects]

        cursor.execute("""
            SELECT tasks.*, projects.name AS project_name
            FROM tasks
            LEFT JOIN projects ON tasks.project_id = projects.id
            WHERE projects.user_id = %s
        """, (user_id,))
        tasks = cursor.fetchall()
        task_list = [dict(zip([column[0] for column in cursor.description], record)) for record in tasks]

        cursor.execute("""
            SELECT comments.*, tasks.title AS task_title
            FROM comments
            LEFT JOIN tasks ON comments.task_id = tasks.id
            LEFT JOIN projects ON tasks.project_id = projects.id
            WHERE projects.user_id = %s
        """, (user_id,))
        comments = cursor.fetchall()
        comment_list = [dict(zip([column[0] for column in cursor.description], record)) for record in comments]

    # Cargar el elemento específico a editar
    item = None
    if item_type == 'project' and item_id:
        cursor.execute("SELECT * FROM projects WHERE id = %s", (item_id,))
        item = cursor.fetchone()

    elif item_type == 'task' and item_id:
        cursor.execute("""
            SELECT tasks.*, projects.name AS project_name
            FROM tasks
            LEFT JOIN projects ON tasks.project_id = projects.id
            WHERE tasks.id = %s
        """, (item_id,))
        item = cursor.fetchone()

    elif item_type == 'comment' and item_id:
        cursor.execute("""
            SELECT comments.*, tasks.title AS task_title
            FROM comments
            LEFT JOIN tasks ON comments.task_id = tasks.id
            LEFT JOIN projects ON tasks.project_id = projects.id
            WHERE comments.id = %s
        """, (item_id,))
        item = cursor.fetchone()

    cursor.close()

    # Renderizar la plantilla con los datos cargados
    return render_template(
        'edit.html',
        projects=project_list,
        tasks=task_list,
        comments=comment_list,
        item_type=item_type,
        item=dict(zip([column[0] for column in cursor.description], item)) if item else None
    )

@app.route('/update_project_status', methods=['POST'])
def update_project_status():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'No autorizado'}), 403

    data = request.get_json()
    project_id = data.get('project_id')
    new_status = data.get('status')

    if new_status not in ['To Do', 'Haciendo', 'Terminado']:
        return jsonify({'success': False, 'message': 'Estado no válido'}), 400

    cursor = db.database.cursor()

    # Verificar si el usuario tiene acceso al proyecto o si es administrador
    if not session.get('is_admin', False):
        cursor.execute("SELECT id FROM projects WHERE id = %s AND user_id = %s", (project_id, session['user_id']))
        project = cursor.fetchone()
        if not project:
            return jsonify({'success': False, 'message': 'Acceso denegado'}), 403

    # Actualizar el estado del proyecto
    cursor.execute("UPDATE projects SET status = %s WHERE id = %s", (new_status, project_id))
    db.database.commit()
    cursor.close()

    return jsonify({'success': True})


@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('is_admin', False):
        flash('No tienes permiso para acceder a esta página.', 'danger')
        return redirect(url_for('notes'))

    cursor = db.database.cursor()

    # Obtener nombres de proyectos y costos totales de tareas
    cursor.execute("""
        SELECT projects.name, SUM(tasks.cost) AS total_cost
        FROM projects
        LEFT JOIN tasks ON projects.id = tasks.project_id
        GROUP BY projects.id, projects.name
    """)
    project_costs_data = cursor.fetchall()
    project_names = [row[0] for row in project_costs_data]
    project_costs = [row[1] if row[1] else 0 for row in project_costs_data]

    # Obtener cantidad de proyectos por estado
    cursor.execute("""
        SELECT status, COUNT(*) 
        FROM projects 
        GROUP BY status
    """)
    project_status_data = cursor.fetchall()
    status_mapping = {'To Do': 0, 'Haciendo': 0, 'Terminado': 0}
    for row in project_status_data:
        status_mapping[row[0]] = row[1]

    cursor.close()

    return render_template(
        'dashboard.html',
        project_names=project_names,
        project_costs=project_costs,
        project_status_counts=list(status_mapping.values())
    )



if __name__ == '__main__':
    app.run(debug=True, port=4000)
