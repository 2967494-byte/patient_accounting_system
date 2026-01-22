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
        messages_desc = Message.query.options(joinedload(Message.reactions), joinedload(Message.sender)).filter(
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
        messages_desc = Message.query.options(joinedload(Message.reactions), joinedload(Message.sender)).filter(
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

    from sqlalchemy import func, or_
    
    search_query = request.args.get('search', '').lower()
    
    # Base query for Org and Doctor users
    query = User.query.filter(User.role.in_(['org', 'doctor']))
    
    if search_query:
        query = query.join(Organization, isouter=True).filter(
            or_(
                func.lower(User.username).contains(search_query),
                func.lower(Organization.name).contains(search_query)
            )
        )
    
    org_users = query.all()
    user_ids = [u.id for u in org_users]
    
    if not user_ids:
        return jsonify([])

    # 1. Get unread counts for all these users (messages to Support)
    unread_counts = db.session.query(
        Message.sender_id, 
        func.count(Message.id).label('count')
    ).filter(
        Message.sender_id.in_(user_ids),
        Message.recipient_id == None,
        Message.is_read == False
    ).group_by(Message.sender_id).all()
    
    unread_map = {u.sender_id: u.count for u in unread_counts}
    
    # 2. Get last messages for all these users
    # Subquery to find max message ID for each "thread" (User <-> Support)
    # A thread is messages where user is sender (to support) OR recipient (from support)
    last_msg_ids = db.session.query(
        func.max(Message.id)
    ).filter(
        or_(
            (Message.sender_id.in_(user_ids)) & (Message.recipient_id == None),
            (Message.recipient_id.in_(user_ids))
        )
    ).group_by(
        func.coalesce(Message.recipient_id, Message.sender_id)
    ).all()
    
    last_msg_ids = [mid[0] for mid in last_msg_ids if mid[0]]
    last_messages_list = Message.query.filter(Message.id.in_(last_msg_ids)).all()
    
    # Map messages to users
    last_msg_map = {}
    for m in last_messages_list:
        uid = m.recipient_id if m.recipient_id else m.sender_id
        # Note: if both are set (not possible in our support schema where one side is always None), 
        # we'd need more complex logic. But here recipient_id=None means sent to Support.
        last_msg_map[uid] = m
    
    threads = []
    for user in org_users:
        last_msg = last_msg_map.get(user.id)
        
        # Filter: If no search query, only show active threads (with messages)
        if not search_query and not last_msg:
            continue
            
        unread_count = unread_map.get(user.id, 0)
        
        if user.role == 'org' and user.organization:
            org_name = user.organization.name
        else:
            org_name = "Врач" if user.role == 'doctor' else "Пользователь"
            
        threads.append({
            'user_id': user.id,
            'username': user.username,
            'org_name': org_name,
            'display_name': f"{user.username} - {org_name}",
            'last_message': last_msg.body if last_msg else '',
            'last_timestamp': last_msg.timestamp.isoformat() + 'Z' if last_msg else None,
            'unread_count': unread_count
        })
    
    # Sort: unread first, then timestamp
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
