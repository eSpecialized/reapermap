"""Safe source file that should remain visible in repository maps."""


def public_feature_flag():
    return "mockrepotest-safe-feature"


class PublicConfig:
    def enabled(self):
        return True

