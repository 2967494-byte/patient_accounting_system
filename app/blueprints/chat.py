from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from app.models import Message, MessageReaction, User, Organization, db
from datetime import datetime

chat = Blueprint('chat', __name__)

@chat.route('/messages/send', methods=['POST'])
@login_required
def send_message():
    data = request.get_json()
    body = data.get('body')
    
    if not body:
        return jsonify({'error': 'Message body empty'}), 400

    # Org sends to Support (recipient_id=None)
    # Support sends to Org (recipient_id=user_id)
    recipient_id = data.get('recipient_id')

    msg = Message(
        sender_id=current_user.id,
        recipient_id=recipient_id,
        body=body,
        timestamp=datetime.now(),
        is_read=False
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify(msg.to_dict()), 201

@chat.route('/messages/history', methods=['GET'])
@login_required
def get_history():
    # If Org: Get own messages (sent or received)
    # If Support (Admin/LabTech): Get messages for specific thread (user_id) or all?
    # Requirement: "Dialogs... left side who wrote... sort by time"
    # This endpoint likely returns messages for a specific interaction.
    
    view_user_id = request.args.get('user_id')
    
    from sqlalchemy.orm import joinedload
    
    if current_user.role in ['org', 'doctor']:
        # Org/Doctor sees only their conversation with Support
        # Messages where (sender=self AND recipient=None) OR (recipient=self)
        # Get last 100 messages (descending)
        messages_desc = Message.query.options(joinedload(Message.reactions)).filter(
            ((Message.sender_id == current_user.id) & (Message.recipient_id == None)) |
            (Message.recipient_id == current_user.id)
        ).order_by(Message.timestamp.desc()).limit(100).all()
        
        # Sort back to ascending for display
        messages = sorted(messages_desc, key=lambda m: m.timestamp)
        
    else:
        # Support Staff
        if not view_user_id:
             return jsonify({'error': 'User ID required'}), 400
        
        try:
            view_user_id = int(view_user_id)
        except ValueError:
            return jsonify({'error': 'Invalid User ID'}), 400
        
        # Messages between Support and that User
        # (sender=User AND recipient=None) OR (sender=Staff?? AND recipient=User)
        # Actually any Support staff can reply. Sender will be `current_user.id`.
        # So thread is defined by the Org User's ID.
        
        # Get last 100 messages (descending)
        messages_desc = Message.query.options(joinedload(Message.reactions)).filter(
            ((Message.sender_id == view_user_id) & (Message.recipient_id == None)) |
            (Message.recipient_id == view_user_id)
        ).order_by(Message.timestamp.desc()).limit(100).all()
        
        # Sort back to ascending for display
        messages = sorted(messages_desc, key=lambda m: m.timestamp)

    return jsonify([m.to_dict() for m in messages])

@chat.route('/threads', methods=['GET'])
@login_required
def get_threads():
    # Only for Support
    if current_user.role in ['org', 'doctor']:
        return jsonify({'error': 'Unauthorized'}), 403

    # Get list of Users (Orgs/Doctors) who have messaged Support
    # Or just all Orgs? Better to show only those with messages or all active.
    # Simple: All Users with role='org' AND (have messages).
    # For MVP: List all 'org' users, with last message preview.
    
    from sqlalchemy import func, or_
    
    search_query = request.args.get('search', '').lower()
    
    # Base query for Org and Doctor users
    query = User.query.filter(User.role.in_(['org', 'doctor']))
    
    if search_query:
        # Search by username or organization name
        query = query.join(Organization).filter(
            or_(
                func.lower(User.username).contains(search_query),
                func.lower(Organization.name).contains(search_query)
            )
        )
    
    orgs = query.all()
    
    threads = []
    for org in orgs:
        # Get last message
        last_msg = Message.query.filter(
            ((Message.sender_id == org.id) & (Message.recipient_id == None)) |
            (Message.recipient_id == org.id)
        ).order_by(Message.timestamp.desc()).first()
        
        # Filter: If no search query, only show active threads (with messages)
        # If searching, show all matches (to allow starting new chat)
        if not search_query and not last_msg:
            continue
            
        # Count unread (sent by Org, recipient=None, is_read=False)
        unread_count = Message.query.filter_by(
            sender_id=org.id,
            recipient_id=None,
            is_read=False
        ).count()
        
        if org.role == 'org' and org.organization:
            org_name = org.organization.name
        else:
            org_name = "Врач" if org.role == 'doctor' else "Пользователь"
            
        display_name = f"{org.username} - {org_name}"
        
        threads.append({
            'user_id': org.id,
            'username': org.username,
            'org_name': org_name,
            'display_name': display_name,
            'last_message': last_msg.body if last_msg else '',
            'last_timestamp': last_msg.timestamp.isoformat() if last_msg else None,
            'unread_count': unread_count
        })
    
    # Sort by unread count desc, then timestamp desc
    threads.sort(key=lambda x: (x['unread_count'], x['last_timestamp'] or ''), reverse=True)
    
    return jsonify(threads)

@chat.route('/messages/read', methods=['POST'])
@login_required
def mark_read():
    data = request.get_json()
    user_id = data.get('user_id') # The Org user ID whose messages we are reading
    
    if current_user.role in ['org', 'doctor']:
        # Org/Doctor reading Support messages
        # Update messages where recipient=current_user
        Message.query.filter_by(recipient_id=current_user.id, is_read=False).update({'is_read': True})
    else:
        # Support reading Org messages
        if not user_id:
            return jsonify({'error': 'User ID required'}), 400
        # Update messages from this user to Support
        Message.query.filter_by(sender_id=user_id, recipient_id=None, is_read=False).update({'is_read': True})
        
    db.session.commit()
    return jsonify({'status': 'ok'})


@chat.route('/messages/<int:message_id>/react', methods=['POST'])
@login_required
def toggle_reaction(message_id):
    """Toggle a reaction on a message (add if not exists, remove if exists)"""
    data = request.get_json()
    emoji = data.get('emoji')
    
    if not emoji or len(emoji) > 10:
        return jsonify({'error': 'Invalid emoji'}), 400
    
    # Check if message exists
    message = Message.query.get_or_404(message_id)
    
    # Check if reaction already exists
    existing = MessageReaction.query.filter_by(
        message_id=message_id,
        user_id=current_user.id,
        emoji=emoji
    ).first()
    
    if existing:
        # Remove reaction (toggle off)
        db.session.delete(existing)
        db.session.commit()
        return jsonify({
            'status': 'removed',
            'reactions': message.get_reactions_summary()
        })
    else:
        # Add reaction (toggle on)
        reaction = MessageReaction(
            message_id=message_id,
            user_id=current_user.id,
            emoji=emoji
        )
        db.session.add(reaction)
        db.session.commit()
        return jsonify({
            'status': 'added',
            'reactions': message.get_reactions_summary()
        })
