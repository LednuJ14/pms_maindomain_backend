"""
Blacklisted Token Model for JWT Token Management
"""
from datetime import datetime
from app import db

class BlacklistedToken(db.Model):
    """
    Token Model for storing JWT tokens that have been blacklisted.
    Used for logout functionality and token revocation.
    """
    __tablename__ = 'blacklisted_tokens'
    
    id = db.Column(db.Integer, primary_key=True)
    # Many schemas store the JWT ID as 'jti'. Our previous model used 'token'.
    # Align with DB by using 'jti' column name.
    jti = db.Column(db.String(500), unique=True, nullable=False)
    # Some schemas call this 'revoked_at' instead of 'blacklisted_on'
    revoked_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    def __init__(self, token, expires_at, user_id=None):
        """Initialize blacklisted token.

        Accepts historical param name 'token' but stores into 'jti'.
        """
        self.jti = token  # store JTI
        self.expires_at = expires_at
        self.user_id = user_id
    
    @classmethod
    def check_blacklist(cls, jti):
        """
        Check if JWT token ID has been blacklisted.
        
        Args:
            jti (str): JWT token ID to check
            
        Returns:
            bool: True if token is blacklisted, False otherwise
        """
        res = cls.query.filter_by(jti=jti).first()
        return bool(res)
    
    @classmethod
    def add_token_to_blacklist(cls, jti, expires_at, user_id=None):
        """
        Add a token to the blacklist.
        
        Args:
            jti (str): JWT token ID to blacklist
            expires_at (datetime): Token expiration date
            user_id (int): Optional user ID
        """
        blacklisted_token = cls(token=jti, expires_at=expires_at, user_id=user_id)
        db.session.add(blacklisted_token)
        db.session.commit()
    
    @classmethod
    def cleanup_expired_tokens(cls):
        """
        Remove expired tokens from blacklist to keep table clean.
        Should be run periodically as a cleanup task.
        """
        expired_tokens = cls.query.filter(cls.expires_at < datetime.utcnow()).all()
        for token in expired_tokens:
            db.session.delete(token)
        db.session.commit()
        return len(expired_tokens)
    
    def __repr__(self):
        """String representation of blacklisted token."""
        # jti may be long; show first chars
        try:
            preview = (self.jti or '')[:20]
        except Exception:
            preview = ''
        return f'<BlacklistedToken {preview}...>'
