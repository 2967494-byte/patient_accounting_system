from app import create_app

app = create_app()

@app.shell_context_processor
def make_shell_context():
    from app.extensions import db
    from app.models import User, Location, Appointment, Organization
    return {'db': db, 'User': User, 'Location': Location, 'Appointment': Appointment, 'Organization': Organization}

if __name__ == '__main__':
    app.run(debug=True)
