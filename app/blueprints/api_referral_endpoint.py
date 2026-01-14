from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db, csrf
from app.models import Appointment, Service, AdditionalService, AppointmentService, AppointmentAdditionalService, Doctor, Clinic, Message, User
from datetime import datetime, timedelta

# ... existing code ...

@api.route('/referral-request', methods=['POST'])
@login_required
def create_referral_request():
    """
    Create a referral request from org user and post it to messenger chat.
    """
    # Only org users can create referral requests
    if current_user.role != 'org':
        return jsonify({'error': 'Unauthorized. Only org users can request referrals.'}), 403
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No input data provided'}), 400
        
        doctor = data.get('doctor', '').strip()
        additional_info = data.get('additional_info', '').strip()
        
        if not doctor:
            return jsonify({'error': 'Doctor name is required'}), 400
        
        # Format message content
        message_text = f"""Запрос на направления

Врач: {doctor}"""
        
        if additional_info:
            message_text += f"\nДоп. информация: {additional_info}"
        
        # Find admin user to send message to (first superadmin or admin)
        admin_user = User.query.filter(User.role.in_(['superadmin', 'admin'])).first()
        
        if not admin_user:
            return jsonify({'error': 'No admin user found to send request to'}), 500
        
        # Create message in chat system
        message = Message(
            sender_id=current_user.id,
            recipient_id=admin_user.id,
            content=message_text,
            timestamp=(datetime.utcnow() + timedelta(hours=3)),
            is_read=False
        )
        
        db.session.add(message)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message_id': message.id,
            'message': 'Referral request sent successfully'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
