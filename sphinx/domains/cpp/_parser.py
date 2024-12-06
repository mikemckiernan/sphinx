from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from sphinx.domains.cpp._ast import (
    ASTAlignofExpr,
    ASTArray,
    ASTAssignmentExpr,
    ASTBaseClass,
    ASTBinOpExpr,
    ASTBooleanLiteral,
    ASTBracedInitList,
    ASTCastExpr,
    ASTCharLiteral,
    ASTClass,
    ASTCommaExpr,
    ASTConcept,
    ASTConditionalExpr,
    ASTDeclaration,
    ASTDeclarator,
    ASTDeclaratorMemPtr,
    ASTDeclaratorNameBitField,
    ASTDeclaratorNameParamQual,
    ASTDeclaratorParamPack,
    ASTDeclaratorParen,
    ASTDeclaratorPtr,
    ASTDeclaratorRef,
    ASTDeclSpecs,
    ASTDeclSpecsSimple,
    ASTDeleteExpr,
    ASTEnum,
    ASTEnumerator,
    ASTExplicitCast,
    ASTExplicitSpec,
    ASTExpression,
    ASTFallbackExpr,
    ASTFoldExpr,
    ASTFunctionParameter,
    ASTIdentifier,
    ASTIdExpression,
    ASTInitializer,
    ASTLiteral,
    ASTNamespace,
    ASTNestedName,
    ASTNestedNameElement,
    ASTNewExpr,
    ASTNoexceptExpr,
    ASTNoexceptSpec,
    ASTNumberLiteral,
    ASTOperator,
    ASTOperatorBuildIn,
    ASTOperatorLiteral,
    ASTOperatorType,
    ASTPackExpansionExpr,
    ASTParametersQualifiers,
    ASTParenExpr,
    ASTParenExprList,
    ASTPointerLiteral,
    ASTPostfixArray,
    ASTPostfixCallExpr,
    ASTPostfixDec,
    ASTPostfixExpr,
    ASTPostfixInc,
    ASTPostfixMember,
    ASTPostfixMemberOfPointer,
    ASTPostfixOp,
    ASTRequiresClause,
    ASTSizeofExpr,
    ASTSizeofParamPack,
    ASTSizeofType,
    ASTStringLiteral,
    ASTTemplateArgConstant,
    ASTTemplateArgs,
    ASTTemplateDeclarationPrefix,
    ASTTemplateIntroduction,
    ASTTemplateIntroductionParameter,
    ASTTemplateKeyParamPackIdDefault,
    ASTTemplateParam,
    ASTTemplateParamConstrainedTypeWithInit,
    ASTTemplateParamNonType,
    ASTTemplateParams,
    ASTTemplateParamTemplateType,
    ASTTemplateParamType,
    ASTThisLiteral,
    ASTTrailingTypeSpec,
    ASTTrailingTypeSpecDecltype,
    ASTTrailingTypeSpecDecltypeAuto,
    ASTTrailingTypeSpecFundamental,
    ASTTrailingTypeSpecName,
    ASTType,
    ASTTypeId,
    ASTTypeUsing,
    ASTTypeWithInit,
    ASTUnaryOpExpr,
    ASTUnion,
    ASTUserDefinedLiteral,
)
from sphinx.domains.cpp._ids import (
    _expression_assignment_ops,
    _expression_bin_ops,
    _expression_unary_ops,
    _fold_operator_re,
    _id_explicit_cast,
    _keywords,
    _operator_re,
    _simple_type_specifiers_re,
    _string_re,
    _visibility_re,
    udl_identifier_re,
)
from sphinx.util import logging
from sphinx.util.cfamily import (
    ASTAttributeList,
    BaseParser,
    DefinitionError,
    UnsupportedMultiCharacterCharLiteral,
    binary_literal_re,
    char_literal_re,
    float_literal_re,
    float_literal_suffix_re,
    hex_literal_re,
    identifier_re,
    integer_literal_re,
    integers_literal_suffix_re,
    octal_literal_re,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

logger = logging.getLogger(__name__)


class DefinitionParser(BaseParser):
    @property
    def language(self) -> str:
        return 'C++'

    @property
    def id_attributes(self) -> Sequence[str]:
        return self.config.cpp_id_attributes

    @property
    def paren_attributes(self) -> Sequence[str]:
        return self.config.cpp_paren_attributes

    def _parse_string(self) -> str:
        if self.current_char != '"':
            return None
        start_pos = self.pos
        self.pos += 1
        escape = False
        while True:
            if self.eof:
                self.fail("Unexpected end during inside string.")
            elif self.current_char == '"' and not escape:
                self.pos += 1
                break
            elif self.current_char == '\\':
                escape = True
            else:
                escape = False
            self.pos += 1
        return self.definition[start_pos:self.pos]

    def _parse_literal(self) -> ASTLiteral:
        # -> integer-literal
        #  | character-literal
        #  | floating-literal
        #  | string-literal
        #  | boolean-literal -> "false" | "true"
        #  | pointer-literal -> "nullptr"
        #  | user-defined-literal

        def _udl(literal: ASTLiteral) -> ASTLiteral:
            if not self.match(udl_identifier_re):
                return literal
            # hmm, should we care if it's a keyword?
            # it looks like GCC does not disallow keywords
            ident = ASTIdentifier(self.matched_text)
            return ASTUserDefinedLiteral(literal, ident)

        self.skip_ws()
        if self.skip_word('nullptr'):
            return ASTPointerLiteral()
        if self.skip_word('true'):
            return ASTBooleanLiteral(True)
        if self.skip_word('false'):
            return ASTBooleanLiteral(False)
        pos = self.pos
        if self.match(float_literal_re):
            has_suffix = self.match(float_literal_suffix_re)
            float_lit = ASTNumberLiteral(self.definition[pos:self.pos])
            if has_suffix:
                return float_lit
            else:
                return _udl(float_lit)
        for regex in (binary_literal_re, hex_literal_re,
                      integer_literal_re, octal_literal_re):
            if self.match(regex):
                has_suffix = self.match(integers_literal_suffix_re)
                int_lit = ASTNumberLiteral(self.definition[pos:self.pos])
                if has_suffix:
                    return int_lit
                else:
                    return _udl(int_lit)

        string = self._parse_string()
        if string is not None:
            return _udl(ASTStringLiteral(string))

        # character-literal
        if self.match(char_literal_re):
            prefix = self.last_match.group(1)  # may be None when no prefix
            data = self.last_match.group(2)
            try:
                char_lit = ASTCharLiteral(prefix, data)
            except UnicodeDecodeError as e:
                self.fail("Can not handle character literal. Internal error was: %s" % e)
            except UnsupportedMultiCharacterCharLiteral:
                self.fail("Can not handle character literal"
                          " resulting in multiple decoded characters.")
            return _udl(char_lit)
        return None

    def _parse_fold_or_paren_expression(self) -> ASTExpression | None:
        # "(" expression ")"
        # fold-expression
        # -> ( cast-expression fold-operator ... )
        #  | ( ... fold-operator cast-expression )
        #  | ( cast-expression fold-operator ... fold-operator cast-expression
        if self.current_char != '(':
            return None
        self.pos += 1
        self.skip_ws()
        if self.skip_string_and_ws("..."):
            # ( ... fold-operator cast-expression )
            if not self.match(_fold_operator_re):
                self.fail("Expected fold operator after '...' in fold expression.")
            op = self.matched_text
            right_expr = self._parse_cast_expression()
            if not self.skip_string(')'):
                self.fail("Expected ')' in end of fold expression.")
            return ASTFoldExpr(None, op, right_expr)
        # try first parsing a unary right fold, or a binary fold
        pos = self.pos
        try:
            self.skip_ws()
            left_expr = self._parse_cast_expression()
            self.skip_ws()
            if not self.match(_fold_operator_re):
                self.fail("Expected fold operator after left expression in fold expression.")
            op = self.matched_text
            self.skip_ws()
            if not self.skip_string_and_ws('...'):
                self.fail("Expected '...' after fold operator in fold expression.")
        except DefinitionError as e_fold:
            self.pos = pos
            # fall back to a paren expression
            try:
                res = self._parse_expression()
                self.skip_ws()
                if not self.skip_string(')'):
                    self.fail("Expected ')' in end of parenthesized expression.")
            except DefinitionError as e_expr:
                raise self._make_multi_error([
                    (e_fold, "If fold expression"),
                    (e_expr, "If parenthesized expression"),
                ], "Error in fold expression or parenthesized expression.") from e_expr
            return ASTParenExpr(res)
        # now it definitely is a fold expression
        if self.skip_string(')'):
            return ASTFoldExpr(left_expr, op, None)
        if not self.match(_fold_operator_re):
            self.fail("Expected fold operator or ')' after '...' in fold expression.")
        if op != self.matched_text:
            self.fail("Operators are different in binary fold: '%s' and '%s'."
                      % (op, self.matched_text))
        right_expr = self._parse_cast_expression()
        self.skip_ws()
        if not self.skip_string(')'):
            self.fail("Expected ')' to end binary fold expression.")
        return ASTFoldExpr(left_expr, op, right_expr)

    def _parse_primary_expression(self) -> ASTExpression:
        # literal
        # "this"
        # lambda-expression
        # "(" expression ")"
        # fold-expression
        # id-expression -> we parse this with _parse_nested_name
        self.skip_ws()
        res: ASTExpression = self._parse_literal()
        if res is not None:
            return res
        self.skip_ws()
        if self.skip_word("this"):
            return ASTThisLiteral()
        # TODO: try lambda expression
        res = self._parse_fold_or_paren_expression()
        if res is not None:
            return res
        nn = self._parse_nested_name()
        if nn is not None:
            return ASTIdExpression(nn)
        return None

    def _parse_initializer_list(self, name: str, open: str, close: str,
                                ) -> tuple[list[ASTExpression | ASTBracedInitList],
                                           bool]:
        # Parse open and close with the actual initializer-list in between
        # -> initializer-clause '...'[opt]
        #  | initializer-list ',' initializer-clause '...'[opt]
        self.skip_ws()
        if not self.skip_string_and_ws(open):
            return None, None
        if self.skip_string(close):
            return [], False

        exprs: list[ASTExpression | ASTBracedInitList] = []
        trailing_comma = False
        while True:
            self.skip_ws()
            expr = self._parse_initializer_clause()
            self.skip_ws()
            if self.skip_string('...'):
                exprs.append(ASTPackExpansionExpr(expr))
            else:
                exprs.append(expr)
            self.skip_ws()
            if self.skip_string(close):
                break
            if not self.skip_string_and_ws(','):
                self.fail(f"Error in {name}, expected ',' or '{close}'.")
            if self.current_char == close == '}':
                self.pos += 1
                trailing_comma = True
                break
        return exprs, trailing_comma

    def _parse_paren_expression_list(self) -> ASTParenExprList:
        # -> '(' expression-list ')'
        # though, we relax it to also allow empty parens
        # as it's needed in some cases
        #
        # expression-list
        # -> initializer-list
        exprs, trailing_comma = self._parse_initializer_list("parenthesized expression-list",
                                                            '(', ')')
        if exprs is None:
            return None
        return ASTParenExprList(exprs)

    def _parse_initializer_clause(self) -> ASTExpression | ASTBracedInitList:
        braced_init_list = self._parse_braced_init_list()
        if braced_init_list is not None:
            return braced_init_list
        return self._parse_assignment_expression(in_template=False)

    def _parse_braced_init_list(self) -> ASTBracedInitList:
        # -> '{' initializer-list ','[opt] '}'
        #  | '{' '}'
        exprs, trailing_comma = self._parse_initializer_list("braced-init-list", '{', '}')
        if exprs is None:
            return None
        return ASTBracedInitList(exprs, trailing_comma)

    def _parse_expression_list_or_braced_init_list(
        self,
    ) -> ASTParenExprList | ASTBracedInitList:
        paren = self._parse_paren_expression_list()
        if paren is not None:
            return paren
        return self._parse_braced_init_list()

    def _parse_postfix_expression(self) -> ASTPostfixExpr:
        # -> primary
        #  | postfix "[" expression "]"
        #  | postfix "[" braced-init-list [opt] "]"
        #  | postfix "(" expression-list [opt] ")"
        #  | postfix "." "template" [opt] id-expression
        #  | postfix "->" "template" [opt] id-expression
        #  | postfix "." pseudo-destructor-name
        #  | postfix "->" pseudo-destructor-name
        #  | postfix "++"
        #  | postfix "--"
        #  | simple-type-specifier "(" expression-list [opt] ")"
        #  | simple-type-specifier braced-init-list
        #  | typename-specifier "(" expression-list [opt] ")"
        #  | typename-specifier braced-init-list
        #  | "dynamic_cast" "<" type-id ">" "(" expression ")"
        #  | "static_cast" "<" type-id ">" "(" expression ")"
        #  | "reinterpret_cast" "<" type-id ">" "(" expression ")"
        #  | "const_cast" "<" type-id ">" "(" expression ")"
        #  | "typeid" "(" expression ")"
        #  | "typeid" "(" type-id ")"

        prefix_type = None
        prefix: Any = None
        self.skip_ws()

        cast = None
        for c in _id_explicit_cast:
            if self.skip_word_and_ws(c):
                cast = c
                break
        if cast is not None:
            prefix_type = "cast"
            if not self.skip_string("<"):
                self.fail("Expected '<' after '%s'." % cast)
            typ = self._parse_type(False)
            self.skip_ws()
            if not self.skip_string_and_ws(">"):
                self.fail("Expected '>' after type in '%s'." % cast)
            if not self.skip_string("("):
                self.fail("Expected '(' in '%s'." % cast)

            def parser() -> ASTExpression:
                return self._parse_expression()
            expr = self._parse_expression_fallback([')'], parser)
            self.skip_ws()
            if not self.skip_string(")"):
                self.fail("Expected ')' to end '%s'." % cast)
            prefix = ASTExplicitCast(cast, typ, expr)
        elif self.skip_word_and_ws("typeid"):
            prefix_type = "typeid"
            if not self.skip_string_and_ws('('):
                self.fail("Expected '(' after 'typeid'.")
            pos = self.pos
            try:
                typ = self._parse_type(False)
                prefix = ASTTypeId(typ, isType=True)
                if not self.skip_string(')'):
                    self.fail("Expected ')' to end 'typeid' of type.")
            except DefinitionError as e_type:
                self.pos = pos
                try:

                    def parser() -> ASTExpression:
                        return self._parse_expression()
                    expr = self._parse_expression_fallback([')'], parser)
                    prefix = ASTTypeId(expr, isType=False)
                    if not self.skip_string(')'):
                        self.fail("Expected ')' to end 'typeid' of expression.")
                except DefinitionError as e_expr:
                    self.pos = pos
                    header = "Error in 'typeid(...)'."
                    header += " Expected type or expression."
                    errors = []
                    errors.append((e_type, "If type"))
                    errors.append((e_expr, "If expression"))
                    raise self._make_multi_error(errors, header) from e_expr
        else:  # a primary expression or a type
            pos = self.pos
            try:
                prefix = self._parse_primary_expression()
                prefix_type = 'expr'
            except DefinitionError as e_outer:
                self.pos = pos
                try:
                    # we are potentially casting, so save parens for us
                    # TODO: hmm, would we need to try both with operatorCast and with None?
                    prefix = self._parse_type(False, 'operatorCast')
                    prefix_type = 'typeOperatorCast'
                    #  | simple-type-specifier "(" expression-list [opt] ")"
                    #  | simple-type-specifier braced-init-list
                    #  | typename-specifier "(" expression-list [opt] ")"
                    #  | typename-specifier braced-init-list
                    self.skip_ws()
                    if self.current_char not in {'(', '{'}:
                        self.fail("Expecting '(' or '{' after type in cast expression.")
                except DefinitionError as e_inner:
                    self.pos = pos
                    header = "Error in postfix expression,"
                    header += " expected primary expression or type."
                    errors = []
                    errors.append((e_outer, "If primary expression"))
                    errors.append((e_inner, "If type"))
                    raise self._make_multi_error(errors, header) from e_inner

        # and now parse postfixes
        post_fixes: list[ASTPostfixOp] = []
        while True:
            self.skip_ws()
            if prefix_type in {'expr', 'cast', 'typeid'}:
                if self.skip_string_and_ws('['):
                    expr = self._parse_expression()
                    self.skip_ws()
                    if not self.skip_string(']'):
                        self.fail("Expected ']' in end of postfix expression.")
                    post_fixes.append(ASTPostfixArray(expr))
                    continue
                if self.skip_string('.'):
                    if self.skip_string('*'):
                        # don't steal the dot
                        self.pos -= 2
                    elif self.skip_string('..'):
                        # don't steal the dot
                        self.pos -= 3
                    else:
                        name = self._parse_nested_name()
                        post_fixes.append(ASTPostfixMember(name))
                        continue
                if self.skip_string('->'):
                    if self.skip_string('*'):
                        # don't steal the arrow
                        self.pos -= 3
                    else:
                        name = self._parse_nested_name()
                        post_fixes.append(ASTPostfixMemberOfPointer(name))
                        continue
                if self.skip_string('++'):
                    post_fixes.append(ASTPostfixInc())
                    continue
                if self.skip_string('--'):
                    post_fixes.append(ASTPostfixDec())
                    continue
            lst = self._parse_expression_list_or_braced_init_list()
            if lst is not None:
                post_fixes.append(ASTPostfixCallExpr(lst))
                continue
            break
        return ASTPostfixExpr(prefix, post_fixes)

    def _parse_unary_expression(self) -> ASTExpression:
        # -> postfix
        #  | "++" cast
        #  | "--" cast
        #  | unary-operator cast -> (* | & | + | - | ! | ~) cast
        # The rest:
        #  | "sizeof" unary
        #  | "sizeof" "(" type-id ")"
        #  | "sizeof" "..." "(" identifier ")"
        #  | "alignof" "(" type-id ")"
        #  | noexcept-expression -> noexcept "(" expression ")"
        #  | new-expression
        #  | delete-expression
        self.skip_ws()
        for op in _expression_unary_ops:
            # TODO: hmm, should we be able to backtrack here?
            if op[0] in 'cn':
                res = self.skip_word(op)
            else:
                res = self.skip_string(op)
            if res:
                expr = self._parse_cast_expression()
                return ASTUnaryOpExpr(op, expr)
        if self.skip_word_and_ws('sizeof'):
            if self.skip_string_and_ws('...'):
                if not self.skip_string_and_ws('('):
                    self.fail("Expecting '(' after 'sizeof...'.")
                if not self.match(identifier_re):
                    self.fail("Expecting identifier for 'sizeof...'.")
                ident = ASTIdentifier(self.matched_text)
                self.skip_ws()
                if not self.skip_string(")"):
                    self.fail("Expecting ')' to end 'sizeof...'.")
                return ASTSizeofParamPack(ident)
            if self.skip_string_and_ws('('):
                typ = self._parse_type(named=False)
                self.skip_ws()
                if not self.skip_string(')'):
                    self.fail("Expecting ')' to end 'sizeof'.")
                return ASTSizeofType(typ)
            expr = self._parse_unary_expression()
            return ASTSizeofExpr(expr)
        if self.skip_word_and_ws('alignof'):
            if not self.skip_string_and_ws('('):
                self.fail("Expecting '(' after 'alignof'.")
            typ = self._parse_type(named=False)
            self.skip_ws()
            if not self.skip_string(')'):
                self.fail("Expecting ')' to end 'alignof'.")
            return ASTAlignofExpr(typ)
        if self.skip_word_and_ws('noexcept'):
            if not self.skip_string_and_ws('('):
                self.fail("Expecting '(' after 'noexcept'.")
            expr = self._parse_expression()
            self.skip_ws()
            if not self.skip_string(')'):
                self.fail("Expecting ')' to end 'noexcept'.")
            return ASTNoexceptExpr(expr)
        # new-expression
        pos = self.pos
        rooted = self.skip_string('::')
        self.skip_ws()
        if not self.skip_word_and_ws('new'):
            self.pos = pos
        else:
            # new-placement[opt] new-type-id new-initializer[opt]
            # new-placement[opt] ( type-id ) new-initializer[opt]
            is_new_type_id = True
            if self.skip_string_and_ws('('):
                # either this is a new-placement or it's the second production
                # without placement, and it's actually the ( type-id ) part
                self.fail("Sorry, neither new-placement nor parenthesised type-id "
                          "in new-epression is supported yet.")
                # set is_new_type_id = False if it's (type-id)
            if is_new_type_id:
                decl_specs = self._parse_decl_specs(outer=None)
                decl = self._parse_declarator(named=False, param_mode="new")
            else:
                self.fail("Sorry, parenthesised type-id in new expression not yet supported.")
            lst = self._parse_expression_list_or_braced_init_list()
            return ASTNewExpr(rooted, is_new_type_id, ASTType(decl_specs, decl), lst)
        # delete-expression
        pos = self.pos
        rooted = self.skip_string('::')
        self.skip_ws()
        if not self.skip_word_and_ws('delete'):
            self.pos = pos
        else:
            array = self.skip_string_and_ws('[')
            if array and not self.skip_string_and_ws(']'):
                self.fail("Expected ']' in array delete-expression.")
            expr = self._parse_cast_expression()
            return ASTDeleteExpr(rooted, array, expr)
        return self._parse_postfix_expression()

    def _parse_cast_expression(self) -> ASTExpression:
        # -> unary  | "(" type-id ")" cast
        pos = self.pos
        self.skip_ws()
        if self.skip_string('('):
            try:
                typ = self._parse_type(False)
                if not self.skip_string(')'):
                    self.fail("Expected ')' in cast expression.")
                expr = self._parse_cast_expression()
                return ASTCastExpr(typ, expr)
            except DefinitionError as ex_cast:
                self.pos = pos
                try:
                    return self._parse_unary_expression()
                except DefinitionError as ex_unary:
                    errs = []
                    errs.append((ex_cast, "If type cast expression"))
                    errs.append((ex_unary, "If unary expression"))
                    raise self._make_multi_error(errs,
                                                 "Error in cast expression.") from ex_unary
        else:
            return self._parse_unary_expression()

    def _parse_logical_or_expression(self, in_template: bool) -> ASTExpression:
        # logical-or     = logical-and      ||
        # logical-and    = inclusive-or     &&
        # inclusive-or   = exclusive-or     |
        # exclusive-or   = and              ^
        # and            = equality         &
        # equality       = relational       ==, !=
        # relational     = shift            <, >, <=, >=, <=>
        # shift          = additive         <<, >>
        # additive       = multiplicative   +, -
        # multiplicative = pm               *, /, %
        # pm             = cast             .*, ->*
        def _parse_bin_op_expr(self: DefinitionParser,
                               op_id: int, in_template: bool) -> ASTExpression:
            if op_id + 1 == len(_expression_bin_ops):
                def parser(in_template: bool) -> ASTExpression:
                    return self._parse_cast_expression()
            else:
                def parser(in_template: bool) -> ASTExpression:
                    return _parse_bin_op_expr(self, op_id + 1, in_template=in_template)
            exprs = []
            ops = []
            exprs.append(parser(in_template=in_template))
            while True:
                self.skip_ws()
                if in_template and self.current_char == '>':
                    break
                pos = self.pos
                one_more = False
                for op in _expression_bin_ops[op_id]:
                    if op[0] in 'abcnox':
                        if not self.skip_word(op):
                            continue
                    else:
                        if not self.skip_string(op):
                            continue
                    if op == self.current_char == '&':
                        # don't split the && 'token'
                        self.pos -= 1
                        # and btw. && has lower precedence, so we are done
                        break
                    try:
                        expr = parser(in_template=in_template)
                        exprs.append(expr)
                        ops.append(op)
                        one_more = True
                        break
                    except DefinitionError:
                        self.pos = pos
                if not one_more:
                    break
            return ASTBinOpExpr(exprs, ops)
        return _parse_bin_op_expr(self, 0, in_template=in_template)

    def _parse_conditional_expression_tail(self, or_expr_head: ASTExpression,
                                           in_template: bool) -> ASTConditionalExpr | None:
        # Consumes the or_expr_head on success.

        # -> "?" expression ":" assignment-expression
        self.skip_ws()
        if not self.skip_string("?"):
            return None
        then_expr = self._parse_expression()
        self.skip_ws()
        if not self.skip_string(":"):
            self.fail('Expected ":" after then-expression in conditional expression.')
        else_expr = self._parse_assignment_expression(in_template)
        return ASTConditionalExpr(or_expr_head, then_expr, else_expr)

    def _parse_assignment_expression(self, in_template: bool) -> ASTExpression:
        # -> conditional-expression
        #  | logical-or-expression assignment-operator initializer-clause
        #  | yield-expression -> "co_yield" assignment-expression
        #                      | "co_yield" braced-init-list
        #  | throw-expression -> "throw" assignment-expression[opt]
        # TODO: yield-expression
        # TODO: throw-expression

        # Now we have (after expanding conditional-expression:
        #     logical-or-expression
        #   | logical-or-expression "?" expression ":" assignment-expression
        #   | logical-or-expression assignment-operator initializer-clause
        left_expr = self._parse_logical_or_expression(in_template=in_template)
        # the ternary operator
        cond_expr = self._parse_conditional_expression_tail(left_expr, in_template)
        if cond_expr is not None:
            return cond_expr
        # and actual assignment
        for op in _expression_assignment_ops:
            if op[0] in 'anox':
                if not self.skip_word(op):
                    continue
            else:
                if not self.skip_string(op):
                    continue
            right_expr = self._parse_initializer_clause()
            return ASTAssignmentExpr(left_expr, op, right_expr)
        # just a logical-or-expression
        return left_expr

    def _parse_constant_expression(self, in_template: bool) -> ASTExpression:
        # -> conditional-expression ->
        #    logical-or-expression
        #  | logical-or-expression "?" expression ":" assignment-expression
        or_expr = self._parse_logical_or_expression(in_template=in_template)
        cond_expr = self._parse_conditional_expression_tail(or_expr, in_template)
        if cond_expr is not None:
            return cond_expr
        return or_expr

    def _parse_expression(self) -> ASTExpression:
        # -> assignment-expression
        #  | expression "," assignment-expression
        exprs = [self._parse_assignment_expression(in_template=False)]
        while True:
            self.skip_ws()
            if not self.skip_string(','):
                break
            exprs.append(self._parse_assignment_expression(in_template=False))
        if len(exprs) == 1:
            return exprs[0]
        else:
            return ASTCommaExpr(exprs)

    def _parse_expression_fallback(self, end: list[str],
                                   parser: Callable[[], ASTExpression],
                                   allow: bool = True) -> ASTExpression:
        # Stupidly "parse" an expression.
        # 'end' should be a list of characters which ends the expression.

        # first try to use the provided parser
        prev_pos = self.pos
        try:
            return parser()
        except DefinitionError as e:
            # some places (e.g., template parameters) we really don't want to use fallback,
            # and for testing we may want to globally disable it
            if not allow or not self.allowFallbackExpressionParsing:
                raise
            self.warn("Parsing of expression failed. Using fallback parser."
                      " Error was:\n%s" % e)
            self.pos = prev_pos
        # and then the fallback scanning
        assert end is not None
        self.skip_ws()
        start_pos = self.pos
        if self.match(_string_re):
            value = self.matched_text
        else:
            # TODO: add handling of more bracket-like things, and quote handling
            brackets = {'(': ')', '{': '}', '[': ']', '<': '>'}
            symbols: list[str] = []
            while not self.eof:
                if len(symbols) == 0 and self.current_char in end:
                    break
                if self.current_char in brackets:
                    symbols.append(brackets[self.current_char])
                elif len(symbols) > 0 and self.current_char == symbols[-1]:
                    symbols.pop()
                self.pos += 1
            if len(end) > 0 and self.eof:
                self.fail("Could not find end of expression starting at %d."
                          % start_pos)
            value = self.definition[start_pos:self.pos].strip()
        return ASTFallbackExpr(value.strip())

    # ==========================================================================

    def _parse_operator(self) -> ASTOperator:
        self.skip_ws()
        # adapted from the old code
        # yay, a regular operator definition
        if self.match(_operator_re):
            return ASTOperatorBuildIn(self.matched_text)

        # new/delete operator?
        for op in 'new', 'delete':
            if not self.skip_word(op):
                continue
            self.skip_ws()
            if self.skip_string('['):
                self.skip_ws()
                if not self.skip_string(']'):
                    self.fail('Expected "]" after  "operator ' + op + '["')
                op += '[]'
            return ASTOperatorBuildIn(op)

        # user-defined literal?
        if self.skip_string('""'):
            self.skip_ws()
            if not self.match(identifier_re):
                self.fail("Expected user-defined literal suffix.")
            identifier = ASTIdentifier(self.matched_text)
            return ASTOperatorLiteral(identifier)

        # oh well, looks like a cast operator definition.
        # In that case, eat another type.
        type = self._parse_type(named=False, outer="operatorCast")
        return ASTOperatorType(type)

    def _parse_template_argument_list(self) -> ASTTemplateArgs:
        # template-argument-list: (but we include the < and > here
        #    template-argument ...[opt]
        #    template-argument-list, template-argument ...[opt]
        # template-argument:
        #    constant-expression
        #    type-id
        #    id-expression
        self.skip_ws()
        if not self.skip_string_and_ws('<'):
            return None
        if self.skip_string('>'):
            return ASTTemplateArgs([], False)
        prev_errors = []
        template_args: list[ASTType | ASTTemplateArgConstant] = []
        pack_expansion = False
        while 1:
            pos = self.pos
            parsed_comma = False
            parsed_end = False
            try:
                type = self._parse_type(named=False)
                self.skip_ws()
                if self.skip_string_and_ws('...'):
                    pack_expansion = True
                    parsed_end = True
                    if not self.skip_string('>'):
                        self.fail('Expected ">" after "..." in template argument list.')
                elif self.skip_string('>'):
                    parsed_end = True
                elif self.skip_string(','):
                    parsed_comma = True
                else:
                    self.fail('Expected "...>", ">" or "," in template argument list.')
                template_args.append(type)
            except DefinitionError as e:
                prev_errors.append((e, "If type argument"))
                self.pos = pos
                try:
                    value = self._parse_constant_expression(in_template=True)
                    self.skip_ws()
                    if self.skip_string_and_ws('...'):
                        pack_expansion = True
                        parsed_end = True
                        if not self.skip_string('>'):
                            self.fail('Expected ">" after "..." in template argument list.')
                    elif self.skip_string('>'):
                        parsed_end = True
                    elif self.skip_string(','):
                        parsed_comma = True
                    else:
                        self.fail('Expected "...>", ">" or "," in template argument list.')
                    template_args.append(ASTTemplateArgConstant(value))
                except DefinitionError as e:
                    self.pos = pos
                    prev_errors.append((e, "If non-type argument"))
                    header = "Error in parsing template argument list."
                    raise self._make_multi_error(prev_errors, header) from e
            if parsed_end:
                assert not parsed_comma
                break
            assert not pack_expansion
        return ASTTemplateArgs(template_args, pack_expansion)

    def _parse_nested_name(self, member_pointer: bool = False) -> ASTNestedName:
        names: list[ASTNestedNameElement] = []
        templates: list[bool] = []

        self.skip_ws()
        rooted = False
        if self.skip_string('::'):
            rooted = True
        while 1:
            self.skip_ws()
            if len(names) > 0:
                template = self.skip_word_and_ws('template')
            else:
                template = False
            templates.append(template)
            ident_or_op: ASTIdentifier | ASTOperator | None = None
            if self.skip_word_and_ws('operator'):
                ident_or_op = self._parse_operator()
            else:
                if not self.match(identifier_re):
                    if member_pointer and len(names) > 0:
                        templates.pop()
                        break
                    self.fail("Expected identifier in nested name.")
                identifier = self.matched_text
                # make sure there isn't a keyword
                if identifier in _keywords:
                    self.fail("Expected identifier in nested name, "
                              "got keyword: %s" % identifier)
                ident_or_op = ASTIdentifier(identifier)
            # try greedily to get template arguments,
            # but otherwise a < might be because we are in an expression
            pos = self.pos
            try:
                template_args = self._parse_template_argument_list()
            except DefinitionError as ex:
                self.pos = pos
                template_args = None
                self.otherErrors.append(ex)
            names.append(ASTNestedNameElement(ident_or_op, template_args))

            self.skip_ws()
            if not self.skip_string('::'):
                if member_pointer:
                    self.fail("Expected '::' in pointer to member (function).")
                break
        return ASTNestedName(names, templates, rooted)

    # ==========================================================================

    def _parse_simple_type_specifiers(self) -> ASTTrailingTypeSpecFundamental:
        modifier: str | None = None
        signedness: str | None = None
        width: list[str] = []
        typ: str | None = None
        names: list[str] = []  # the parsed sequence

        self.skip_ws()
        while self.match(_simple_type_specifiers_re):
            t = self.matched_text
            names.append(t)
            if t in {'auto', 'void', 'bool',
                     'char', 'wchar_t', 'char8_t', 'char16_t', 'char32_t',
                     'int', '__int64', '__int128',
                     'float', 'double',
                     '__float80', '_Float64x', '__float128', '_Float128'}:
                if typ is not None:
                    self.fail(f"Can not have both {t} and {typ}.")
                typ = t
            elif t in {'signed', 'unsigned'}:
                if signedness is not None:
                    self.fail(f"Can not have both {t} and {signedness}.")
                signedness = t
            elif t == 'short':
                if len(width) != 0:
                    self.fail(f"Can not have both {t} and {width[0]}.")
                width.append(t)
            elif t == 'long':
                if len(width) != 0 and width[0] != 'long':
                    self.fail(f"Can not have both {t} and {width[0]}.")
                width.append(t)
            elif t in {'_Imaginary', '_Complex'}:
                if modifier is not None:
                    self.fail(f"Can not have both {t} and {modifier}.")
                modifier = t
            self.skip_ws()
        if len(names) == 0:
            return None

        if typ in {'auto', 'void', 'bool',
                   'wchar_t', 'char8_t', 'char16_t', 'char32_t',
                   '__float80', '_Float64x', '__float128', '_Float128'}:
            if modifier is not None:
                self.fail(f"Can not have both {typ} and {modifier}.")
            if signedness is not None:
                self.fail(f"Can not have both {typ} and {signedness}.")
            if len(width) != 0:
                self.fail(f"Can not have both {typ} and {' '.join(width)}.")
        elif typ == 'char':
            if modifier is not None:
                self.fail(f"Can not have both {typ} and {modifier}.")
            if len(width) != 0:
                self.fail(f"Can not have both {typ} and {' '.join(width)}.")
        elif typ == 'int':
            if modifier is not None:
                self.fail(f"Can not have both {typ} and {modifier}.")
        elif typ in {'__int64', '__int128'}:
            if modifier is not None:
                self.fail(f"Can not have both {typ} and {modifier}.")
            if len(width) != 0:
                self.fail(f"Can not have both {typ} and {' '.join(width)}.")
        elif typ == 'float':
            if signedness is not None:
                self.fail(f"Can not have both {typ} and {signedness}.")
            if len(width) != 0:
                self.fail(f"Can not have both {typ} and {' '.join(width)}.")
        elif typ == 'double':
            if signedness is not None:
                self.fail(f"Can not have both {typ} and {signedness}.")
            if len(width) > 1:
                self.fail(f"Can not have both {typ} and {' '.join(width)}.")
            if len(width) == 1 and width[0] != 'long':
                self.fail(f"Can not have both {typ} and {' '.join(width)}.")
        elif typ is None:
            if modifier is not None:
                self.fail(f"Can not have {modifier} without a floating point type.")
        else:
            msg = f'Unhandled type {typ}'
            raise AssertionError(msg)

        canon_names: list[str] = []
        if modifier is not None:
            canon_names.append(modifier)
        if signedness is not None:
            canon_names.append(signedness)
        canon_names.extend(width)
        if typ is not None:
            canon_names.append(typ)
        return ASTTrailingTypeSpecFundamental(names, canon_names)

    def _parse_trailing_type_spec(self) -> ASTTrailingTypeSpec:
        # fundamental types, https://en.cppreference.com/w/cpp/language/type
        # and extensions
        self.skip_ws()
        res = self._parse_simple_type_specifiers()
        if res is not None:
            return res

        # decltype
        self.skip_ws()
        if self.skip_word_and_ws('decltype'):
            if not self.skip_string_and_ws('('):
                self.fail("Expected '(' after 'decltype'.")
            if self.skip_word_and_ws('auto'):
                if not self.skip_string(')'):
                    self.fail("Expected ')' after 'decltype(auto'.")
                return ASTTrailingTypeSpecDecltypeAuto()
            expr = self._parse_expression()
            self.skip_ws()
            if not self.skip_string(')'):
                self.fail("Expected ')' after 'decltype(<expr>'.")
            return ASTTrailingTypeSpecDecltype(expr)

        # prefixed
        prefix = None
        self.skip_ws()
        for k in ('class', 'struct', 'enum', 'union', 'typename'):
            if self.skip_word_and_ws(k):
                prefix = k
                break
        nested_name = self._parse_nested_name()
        self.skip_ws()
        placeholder_type = None
        if self.skip_word('auto'):
            placeholder_type = 'auto'
        elif self.skip_word_and_ws('decltype'):
            if not self.skip_string_and_ws('('):
                self.fail("Expected '(' after 'decltype' in placeholder type specifier.")
            if not self.skip_word_and_ws('auto'):
                self.fail("Expected 'auto' after 'decltype(' in placeholder type specifier.")
            if not self.skip_string_and_ws(')'):
                self.fail("Expected ')' after 'decltype(auto' in placeholder type specifier.")
            placeholder_type = 'decltype(auto)'
        return ASTTrailingTypeSpecName(prefix, nested_name, placeholder_type)

    def _parse_parameters_and_qualifiers(
        self, param_mode: str,
    ) -> ASTParametersQualifiers | None:
        if param_mode == 'new':
            return None
        self.skip_ws()
        if not self.skip_string('('):
            if param_mode == 'function':
                self.fail('Expecting "(" in parameters-and-qualifiers.')
            else:
                return None
        args = []
        self.skip_ws()
        if not self.skip_string(')'):
            while 1:
                self.skip_ws()
                if self.skip_string('...'):
                    args.append(ASTFunctionParameter(None, True))
                    self.skip_ws()
                    if not self.skip_string(')'):
                        self.fail('Expected ")" after "..." in '
                                  'parameters-and-qualifiers.')
                    break
                # note: it seems that function arguments can always be named,
                # even in function pointers and similar.
                arg = self._parse_type_with_init(outer=None, named='single')
                # TODO: parse default parameters # TODO: didn't we just do that?
                args.append(ASTFunctionParameter(arg))

                self.skip_ws()
                if self.skip_string(','):
                    continue
                if self.skip_string(')'):
                    break
                self.fail('Expecting "," or ")" in parameters-and-qualifiers, '
                          f'got "{self.current_char}".')

        self.skip_ws()
        const = self.skip_word_and_ws('const')
        volatile = self.skip_word_and_ws('volatile')
        if not const:  # the can be permuted
            const = self.skip_word_and_ws('const')

        ref_qual = None
        if self.skip_string('&&'):
            ref_qual = '&&'
        if not ref_qual and self.skip_string('&'):
            ref_qual = '&'

        exception_spec = None
        self.skip_ws()
        if self.skip_string('noexcept'):
            if self.skip_string_and_ws('('):
                expr = self._parse_constant_expression(False)
                self.skip_ws()
                if not self.skip_string(')'):
                    self.fail("Expecting ')' to end 'noexcept'.")
                exception_spec = ASTNoexceptSpec(expr)
            else:
                exception_spec = ASTNoexceptSpec(None)

        self.skip_ws()
        if self.skip_string('->'):
            trailing_return = self._parse_type(named=False)
        else:
            trailing_return = None

        self.skip_ws()
        override = self.skip_word_and_ws('override')
        final = self.skip_word_and_ws('final')
        if not override:
            override = self.skip_word_and_ws(
                'override')  # they can be permuted

        attrs = self._parse_attribute_list()

        self.skip_ws()
        initializer = None
        # if this is a function pointer we should not swallow an initializer
        if param_mode == 'function' and self.skip_string('='):
            self.skip_ws()
            valid = ('0', 'delete', 'default')
            for w in valid:
                if self.skip_word_and_ws(w):
                    initializer = w
                    break
            if not initializer:
                self.fail(
                    'Expected "%s" in initializer-specifier.'
                    % '" or "'.join(valid))

        return ASTParametersQualifiers(
            args, volatile, const, ref_qual, exception_spec, trailing_return,
            override, final, attrs, initializer)

    def _parse_decl_specs_simple(self, outer: str, typed: bool) -> ASTDeclSpecsSimple:
        """Just parse the simple ones."""
        storage = None
        thread_local = None
        inline = None
        virtual = None
        explicit_spec = None
        consteval = None
        constexpr = None
        constinit = None
        volatile = None
        const = None
        friend = None
        attrs = []
        while 1:  # accept any permutation of a subset of some decl-specs
            self.skip_ws()
            if not const and typed:
                const = self.skip_word('const')
                if const:
                    continue
            if not volatile and typed:
                volatile = self.skip_word('volatile')
                if volatile:
                    continue
            if not storage:
                if outer in {'member', 'function'}:
                    if self.skip_word('static'):
                        storage = 'static'
                        continue
                    if self.skip_word('extern'):
                        storage = 'extern'
                        continue
                if outer == 'member':
                    if self.skip_word('mutable'):
                        storage = 'mutable'
                        continue
                if self.skip_word('register'):
                    storage = 'register'
                    continue
            if not inline and outer in {'function', 'member'}:
                inline = self.skip_word('inline')
                if inline:
                    continue
            if not constexpr and outer in {'member', 'function'}:
                constexpr = self.skip_word("constexpr")
                if constexpr:
                    continue

            if outer == 'member':
                if not constinit:
                    constinit = self.skip_word('constinit')
                    if constinit:
                        continue
                if not thread_local:
                    thread_local = self.skip_word('thread_local')
                    if thread_local:
                        continue
            if outer == 'function':
                if not consteval:
                    consteval = self.skip_word('consteval')
                    if consteval:
                        continue
                if not friend:
                    friend = self.skip_word('friend')
                    if friend:
                        continue
                if not virtual:
                    virtual = self.skip_word('virtual')
                    if virtual:
                        continue
                if not explicit_spec:
                    explicit = self.skip_word_and_ws('explicit')
                    if explicit:
                        expr: ASTExpression = None
                        if self.skip_string('('):
                            expr = self._parse_constant_expression(in_template=False)
                            if not expr:
                                self.fail("Expected constant expression after '('"
                                          " in explicit specifier.")
                            self.skip_ws()
                            if not self.skip_string(')'):
                                self.fail("Expected ')' to end explicit specifier.")
                        explicit_spec = ASTExplicitSpec(expr)
                        continue
            attr = self._parse_attribute()
            if attr:
                attrs.append(attr)
                continue
            break
        return ASTDeclSpecsSimple(storage, thread_local, inline, virtual,
                                  explicit_spec, consteval, constexpr, constinit,
                                  volatile, const, friend, ASTAttributeList(attrs))

    def _parse_decl_specs(self, outer: str, typed: bool = True) -> ASTDeclSpecs:
        if outer:
            if outer not in {'type', 'member', 'function', 'templateParam'}:
                raise Exception('Internal error, unknown outer "%s".' % outer)
        """
        storage-class-specifier function-specifier "constexpr"
        "volatile" "const" trailing-type-specifier

        storage-class-specifier ->
              "static" (only for member_object and function_object)
            | "register"

        function-specifier -> "inline" | "virtual" | "explicit" (only for
        function_object)

        "constexpr" (only for member_object and function_object)
        """
        left_specs = self._parse_decl_specs_simple(outer, typed)
        right_specs = None

        if typed:
            trailing = self._parse_trailing_type_spec()
            right_specs = self._parse_decl_specs_simple(outer, typed)
        else:
            trailing = None
        return ASTDeclSpecs(outer, left_specs, right_specs, trailing)

    def _parse_declarator_name_suffix(
        self, named: bool | str, param_mode: str, typed: bool,
    ) -> ASTDeclaratorNameParamQual | ASTDeclaratorNameBitField:
        # now we should parse the name, and then suffixes
        if named == 'maybe':
            pos = self.pos
            try:
                decl_id = self._parse_nested_name()
            except DefinitionError:
                self.pos = pos
                decl_id = None
        elif named == 'single':
            if self.match(identifier_re):
                identifier = ASTIdentifier(self.matched_text)
                nne = ASTNestedNameElement(identifier, None)
                decl_id = ASTNestedName([nne], [False], rooted=False)
                # if it's a member pointer, we may have '::', which should be an error
                self.skip_ws()
                if self.current_char == ':':
                    self.fail("Unexpected ':' after identifier.")
            else:
                decl_id = None
        elif named:
            decl_id = self._parse_nested_name()
        else:
            decl_id = None
        array_ops = []
        while 1:
            self.skip_ws()
            if typed and self.skip_string('['):
                self.skip_ws()
                if self.skip_string(']'):
                    array_ops.append(ASTArray(None))
                    continue

                def parser() -> ASTExpression:
                    return self._parse_expression()
                value = self._parse_expression_fallback([']'], parser)
                if not self.skip_string(']'):
                    self.fail("Expected ']' in end of array operator.")
                array_ops.append(ASTArray(value))
                continue
            break
        param_qual = self._parse_parameters_and_qualifiers(param_mode)
        if param_qual is None and len(array_ops) == 0:
            # perhaps a bit-field
            if named and param_mode == 'type' and typed:
                self.skip_ws()
                if self.skip_string(':'):
                    size = self._parse_constant_expression(in_template=False)
                    return ASTDeclaratorNameBitField(declId=decl_id, size=size)
        return ASTDeclaratorNameParamQual(declId=decl_id, arrayOps=array_ops,
                                          paramQual=param_qual)

    def _parse_declarator(self, named: bool | str, param_mode: str,
                          typed: bool = True,
                          ) -> ASTDeclarator:
        # 'typed' here means 'parse return type stuff'
        if param_mode not in {'type', 'function', 'operatorCast', 'new'}:
            raise Exception(
                "Internal error, unknown param_mode '%s'." % param_mode)
        prev_errors = []
        self.skip_ws()
        if typed and self.skip_string('*'):
            self.skip_ws()
            volatile = False
            const = False
            attr_list = []
            while 1:
                if not volatile:
                    volatile = self.skip_word_and_ws('volatile')
                    if volatile:
                        continue
                if not const:
                    const = self.skip_word_and_ws('const')
                    if const:
                        continue
                attr = self._parse_attribute()
                if attr is not None:
                    attr_list.append(attr)
                    continue
                break
            next = self._parse_declarator(named, param_mode, typed)
            return ASTDeclaratorPtr(next=next, volatile=volatile, const=const,
                                    attrs=ASTAttributeList(attr_list))
        # TODO: shouldn't we parse an R-value ref here first?
        if typed and self.skip_string("&"):
            attrs = self._parse_attribute_list()
            next = self._parse_declarator(named, param_mode, typed)
            return ASTDeclaratorRef(next=next, attrs=attrs)
        if typed and self.skip_string("..."):
            next = self._parse_declarator(named, param_mode, False)
            return ASTDeclaratorParamPack(next=next)
        if typed and self.current_char == '(':  # note: peeking, not skipping
            if param_mode == "operatorCast":
                # TODO: we should be able to parse cast operators which return
                # function pointers. For now, just hax it and ignore.
                return ASTDeclaratorNameParamQual(declId=None, arrayOps=[],
                                                  paramQual=None)
            # maybe this is the beginning of params and quals,try that first,
            # otherwise assume it's noptr->declarator > ( ptr-declarator )
            pos = self.pos
            try:
                # assume this is params and quals
                res = self._parse_declarator_name_suffix(named, param_mode,
                                                         typed)
                return res
            except DefinitionError as ex_param_qual:
                prev_errors.append((ex_param_qual,
                                   "If declarator-id with parameters-and-qualifiers"))
                self.pos = pos
                try:
                    assert self.current_char == '('
                    self.skip_string('(')
                    # TODO: hmm, if there is a name, it must be in inner, right?
                    # TODO: hmm, if there must be parameters, they must be
                    #       inside, right?
                    inner = self._parse_declarator(named, param_mode, typed)
                    if not self.skip_string(')'):
                        self.fail("Expected ')' in \"( ptr-declarator )\"")
                    next = self._parse_declarator(named=False,
                                                  param_mode="type",
                                                  typed=typed)
                    return ASTDeclaratorParen(inner=inner, next=next)
                except DefinitionError as ex_no_ptr_paren:
                    self.pos = pos
                    prev_errors.append((ex_no_ptr_paren, "If parenthesis in noptr-declarator"))
                    header = "Error in declarator"
                    raise self._make_multi_error(prev_errors, header) from ex_no_ptr_paren
        if typed:  # pointer to member
            pos = self.pos
            try:
                name = self._parse_nested_name(member_pointer=True)
                self.skip_ws()
                if not self.skip_string('*'):
                    self.fail("Expected '*' in pointer to member declarator.")
                self.skip_ws()
            except DefinitionError as e:
                self.pos = pos
                prev_errors.append((e, "If pointer to member declarator"))
            else:
                volatile = False
                const = False
                while 1:
                    if not volatile:
                        volatile = self.skip_word_and_ws('volatile')
                        if volatile:
                            continue
                    if not const:
                        const = self.skip_word_and_ws('const')
                        if const:
                            continue
                    break
                next = self._parse_declarator(named, param_mode, typed)
                return ASTDeclaratorMemPtr(name, const, volatile, next=next)
        pos = self.pos
        try:
            res = self._parse_declarator_name_suffix(named, param_mode, typed)
            # this is a heuristic for error messages, for when there is a < after a
            # nested name, but it was not a successful template argument list
            if self.current_char == '<':
                self.otherErrors.append(self._make_multi_error(prev_errors, ""))
            return res
        except DefinitionError as e:
            self.pos = pos
            prev_errors.append((e, "If declarator-id"))
            header = "Error in declarator or parameters-and-qualifiers"
            raise self._make_multi_error(prev_errors, header) from e

    def _parse_initializer(self, outer: str | None = None, allow_fallback: bool = True,
                           ) -> ASTInitializer | None:
        # initializer                           # global vars
        # -> brace-or-equal-initializer
        #  | '(' expression-list ')'
        #
        # brace-or-equal-initializer            # member vars
        # -> '=' initializer-clause
        #  | braced-init-list
        #
        # initializer-clause  # function params, non-type template params (with '=' in front)
        # -> assignment-expression
        #  | braced-init-list
        #
        # we don't distinguish between global and member vars, so disallow paren:
        #
        # -> braced-init-list             # var only
        #  | '=' assignment-expression
        #  | '=' braced-init-list
        self.skip_ws()
        if outer == 'member':
            braced_init = self._parse_braced_init_list()
            if braced_init is not None:
                return ASTInitializer(braced_init, hasAssign=False)

        if not self.skip_string('='):
            return None

        braced_init = self._parse_braced_init_list()
        if braced_init is not None:
            return ASTInitializer(braced_init)

        if outer == 'member':
            fallback_end: list[str] = []
        elif outer == 'templateParam':
            fallback_end = [',', '>']
        elif outer is None:  # function parameter
            fallback_end = [',', ')']
        else:
            self.fail("Internal error, initializer for outer '%s' not "
                      "implemented." % outer)

        in_template = outer == 'templateParam'

        def parser() -> ASTExpression:
            return self._parse_assignment_expression(in_template=in_template)
        value = self._parse_expression_fallback(fallback_end, parser, allow=allow_fallback)
        return ASTInitializer(value)

    def _parse_type(self, named: bool | str, outer: str | None = None) -> ASTType:
        """
        named=False|'maybe'|True: 'maybe' is e.g., for function objects which
        doesn't need to name the arguments

        outer == operatorCast: annoying case, we should not take the params
        """
        if outer:  # always named
            if outer not in {'type', 'member', 'function',
                             'operatorCast', 'templateParam'}:
                raise Exception('Internal error, unknown outer "%s".' % outer)
            if outer != 'operatorCast':
                assert named
        if outer in {'type', 'function'}:
            # We allow type objects to just be a name.
            # Some functions don't have normal return types: constructors,
            # destructors, cast operators
            prev_errors = []
            start_pos = self.pos
            # first try without the type
            try:
                decl_specs = self._parse_decl_specs(outer=outer, typed=False)
                decl = self._parse_declarator(named=True, param_mode=outer,
                                              typed=False)
                must_end = True
                if outer == 'function':
                    # Allow trailing requires on functions.
                    self.skip_ws()
                    if re.compile(r'requires\b').match(self.definition, self.pos):
                        must_end = False
                if must_end:
                    self.assert_end(allowSemicolon=True)
            except DefinitionError as ex_untyped:
                if outer == 'type':
                    desc = "If just a name"
                elif outer == 'function':
                    desc = "If the function has no return type"
                else:
                    raise AssertionError from ex_untyped
                prev_errors.append((ex_untyped, desc))
                self.pos = start_pos
                try:
                    decl_specs = self._parse_decl_specs(outer=outer)
                    decl = self._parse_declarator(named=True, param_mode=outer)
                except DefinitionError as ex_typed:
                    self.pos = start_pos
                    if outer == 'type':
                        desc = "If typedef-like declaration"
                    elif outer == 'function':
                        desc = "If the function has a return type"
                    else:
                        raise AssertionError from ex_untyped
                    prev_errors.append((ex_typed, desc))
                    # Retain the else branch for easier debugging.
                    # TODO: it would be nice to save the previous stacktrace
                    #       and output it here.
                    if True:
                        if outer == 'type':
                            header = "Type must be either just a name or a "
                            header += "typedef-like declaration."
                        elif outer == 'function':
                            header = "Error when parsing function declaration."
                        else:
                            raise AssertionError from ex_untyped
                        raise self._make_multi_error(prev_errors, header) from ex_typed
                    else:  # NoQA: RET506
                        # For testing purposes.
                        # do it again to get the proper traceback (how do you
                        # reliably save a traceback when an exception is
                        # constructed?)
                        self.pos = start_pos
                        typed = True
                        decl_specs = self._parse_decl_specs(outer=outer, typed=typed)
                        decl = self._parse_declarator(named=True, param_mode=outer,
                                                      typed=typed)
        else:
            param_mode = 'type'
            if outer == 'member':
                named = True
            elif outer == 'operatorCast':
                param_mode = 'operatorCast'
                outer = None
            elif outer == 'templateParam':
                named = 'single'
            decl_specs = self._parse_decl_specs(outer=outer)
            decl = self._parse_declarator(named=named, param_mode=param_mode)
        return ASTType(decl_specs, decl)

    def _parse_type_with_init(
            self, named: bool | str,
            outer: str) -> ASTTypeWithInit | ASTTemplateParamConstrainedTypeWithInit:
        if outer:
            assert outer in {'type', 'member', 'function', 'templateParam'}
        type = self._parse_type(outer=outer, named=named)
        if outer != 'templateParam':
            init = self._parse_initializer(outer=outer)
            return ASTTypeWithInit(type, init)
        # it could also be a constrained type parameter, e.g., C T = int&
        pos = self.pos
        e_expr = None
        try:
            init = self._parse_initializer(outer=outer, allow_fallback=False)
            # note: init may be None if there is no =
            if init is None:
                return ASTTypeWithInit(type, None)
            # we parsed an expression, so we must have a , or a >,
            # otherwise the expression didn't get everything
            self.skip_ws()
            if self.current_char not in {',', '>'}:
                # pretend it didn't happen
                self.pos = pos
                init = None
            else:
                # we assume that it was indeed an expression
                return ASTTypeWithInit(type, init)
        except DefinitionError as e:
            self.pos = pos
            e_expr = e
        if not self.skip_string("="):
            return ASTTypeWithInit(type, None)
        try:
            type_init = self._parse_type(named=False, outer=None)
            return ASTTemplateParamConstrainedTypeWithInit(type, type_init)
        except DefinitionError as e_type:
            if e_expr is None:
                raise
            errs = []
            errs.append((e_expr, "If default template argument is an expression"))
            errs.append((e_type, "If default template argument is a type"))
            msg = "Error in non-type template parameter"
            msg += " or constrained template parameter."
            raise self._make_multi_error(errs, msg) from e_type

    def _parse_type_using(self) -> ASTTypeUsing:
        name = self._parse_nested_name()
        self.skip_ws()
        if not self.skip_string('='):
            return ASTTypeUsing(name, None)
        type = self._parse_type(False, None)
        return ASTTypeUsing(name, type)

    def _parse_concept(self) -> ASTConcept:
        nested_name = self._parse_nested_name()
        self.skip_ws()
        initializer = self._parse_initializer('member')
        return ASTConcept(nested_name, initializer)

    def _parse_class(self) -> ASTClass:
        attrs = self._parse_attribute_list()
        name = self._parse_nested_name()
        self.skip_ws()
        final = self.skip_word_and_ws('final')
        bases = []
        self.skip_ws()
        if self.skip_string(':'):
            while 1:
                self.skip_ws()
                visibility = None
                virtual = False
                pack = False
                if self.skip_word_and_ws('virtual'):
                    virtual = True
                if self.match(_visibility_re):
                    visibility = self.matched_text
                    self.skip_ws()
                if not virtual and self.skip_word_and_ws('virtual'):
                    virtual = True
                base_name = self._parse_nested_name()
                self.skip_ws()
                pack = self.skip_string('...')
                bases.append(ASTBaseClass(base_name, visibility, virtual, pack))
                self.skip_ws()
                if self.skip_string(','):
                    continue
                break
        return ASTClass(name, final, bases, attrs)

    def _parse_union(self) -> ASTUnion:
        attrs = self._parse_attribute_list()
        name = self._parse_nested_name()
        return ASTUnion(name, attrs)

    def _parse_enum(self) -> ASTEnum:
        scoped = None  # is set by CPPEnumObject
        attrs = self._parse_attribute_list()
        name = self._parse_nested_name()
        self.skip_ws()
        underlying_type = None
        if self.skip_string(':'):
            underlying_type = self._parse_type(named=False)
        return ASTEnum(name, scoped, underlying_type, attrs)

    def _parse_enumerator(self) -> ASTEnumerator:
        name = self._parse_nested_name()
        attrs = self._parse_attribute_list()
        self.skip_ws()
        init = None
        if self.skip_string('='):
            self.skip_ws()

            def parser() -> ASTExpression:
                return self._parse_constant_expression(in_template=False)
            init_val = self._parse_expression_fallback([], parser)
            init = ASTInitializer(init_val)
        return ASTEnumerator(name, init, attrs)

    # ==========================================================================

    def _parse_template_parameter(self) -> ASTTemplateParam:
        self.skip_ws()
        if self.skip_word('template'):
            # declare a template template parameter
            nested_params = self._parse_template_parameter_list()
        else:
            nested_params = None

        pos = self.pos
        try:
            # Unconstrained type parameter or template type parameter
            key = None
            self.skip_ws()
            if self.skip_word_and_ws('typename'):
                key = 'typename'
            elif self.skip_word_and_ws('class'):
                key = 'class'
            elif nested_params:
                self.fail("Expected 'typename' or 'class' after "
                          "template template parameter list.")
            else:
                self.fail("Expected 'typename' or 'class' in the "
                          "beginning of template type parameter.")
            self.skip_ws()
            parameter_pack = self.skip_string('...')
            self.skip_ws()
            if self.match(identifier_re):
                identifier = ASTIdentifier(self.matched_text)
            else:
                identifier = None
            self.skip_ws()
            if not parameter_pack and self.skip_string('='):
                default = self._parse_type(named=False, outer=None)
            else:
                default = None
                if self.current_char not in ',>':
                    self.fail('Expected "," or ">" after (template) type parameter.')
            data = ASTTemplateKeyParamPackIdDefault(key, identifier,
                                                    parameter_pack, default)
            if nested_params:
                return ASTTemplateParamTemplateType(nested_params, data)
            else:
                return ASTTemplateParamType(data)
        except DefinitionError as e_type:
            if nested_params:
                raise
            try:
                # non-type parameter or constrained type parameter
                self.pos = pos
                param = self._parse_type_with_init('maybe', 'templateParam')
                self.skip_ws()
                parameter_pack = self.skip_string('...')
                return ASTTemplateParamNonType(param, parameter_pack)
            except DefinitionError as e_non_type:
                self.pos = pos
                header = "Error when parsing template parameter."
                errs = []
                errs.append(
                    (e_type, "If unconstrained type parameter or template type parameter"))
                errs.append(
                    (e_non_type, "If constrained type parameter or non-type parameter"))
                raise self._make_multi_error(errs, header) from None

    def _parse_template_parameter_list(self) -> ASTTemplateParams:
        # only: '<' parameter-list '>'
        # we assume that 'template' has just been parsed
        template_params: list[ASTTemplateParam] = []
        self.skip_ws()
        if not self.skip_string("<"):
            self.fail("Expected '<' after 'template'")
        while 1:
            pos = self.pos
            err = None
            try:
                param = self._parse_template_parameter()
                template_params.append(param)
            except DefinitionError as e_param:
                self.pos = pos
                err = e_param
            self.skip_ws()
            if self.skip_string('>'):
                requires_clause = self._parse_requires_clause()
                return ASTTemplateParams(template_params, requires_clause)
            elif self.skip_string(','):
                continue
            else:
                header = "Error in template parameter list."
                errs = []
                if err:
                    errs.append((err, "If parameter"))
                try:
                    self.fail('Expected "," or ">".')
                except DefinitionError as e:
                    errs.append((e, "If no parameter"))
                logger.debug(errs)
                raise self._make_multi_error(errs, header)

    def _parse_template_introduction(self) -> ASTTemplateIntroduction | None:
        pos = self.pos
        try:
            concept = self._parse_nested_name()
        except Exception:
            self.pos = pos
            return None
        self.skip_ws()
        if not self.skip_string('{'):
            self.pos = pos
            return None

        # for sure it must be a template introduction now
        params = []
        while 1:
            self.skip_ws()
            parameter_pack = self.skip_string('...')
            self.skip_ws()
            if not self.match(identifier_re):
                self.fail("Expected identifier in template introduction list.")
            txt_identifier = self.matched_text
            # make sure there isn't a keyword
            if txt_identifier in _keywords:
                self.fail("Expected identifier in template introduction list, "
                          "got keyword: %s" % txt_identifier)
            identifier = ASTIdentifier(txt_identifier)
            params.append(ASTTemplateIntroductionParameter(identifier, parameter_pack))

            self.skip_ws()
            if self.skip_string('}'):
                break
            if self.skip_string(','):
                continue
            self.fail('Error in template introduction list. Expected ",", or "}".')
        return ASTTemplateIntroduction(concept, params)

    def _parse_requires_clause(self) -> ASTRequiresClause | None:
        # requires-clause -> 'requires' constraint-logical-or-expression
        # constraint-logical-or-expression
        #   -> constraint-logical-and-expression
        #    | constraint-logical-or-expression '||' constraint-logical-and-expression
        # constraint-logical-and-expression
        #   -> primary-expression
        #    | constraint-logical-and-expression '&&' primary-expression
        self.skip_ws()
        if not self.skip_word('requires'):
            return None

        def parse_and_expr(self: DefinitionParser) -> ASTExpression:
            and_exprs = []
            ops = []
            and_exprs.append(self._parse_primary_expression())
            while True:
                self.skip_ws()
                one_more = False
                if self.skip_string('&&'):
                    one_more = True
                    ops.append('&&')
                elif self.skip_word('and'):
                    one_more = True
                    ops.append('and')
                if not one_more:
                    break
                and_exprs.append(self._parse_primary_expression())
            if len(and_exprs) == 1:
                return and_exprs[0]
            else:
                return ASTBinOpExpr(and_exprs, ops)

        or_exprs = []
        ops = []
        or_exprs.append(parse_and_expr(self))
        while True:
            self.skip_ws()
            one_more = False
            if self.skip_string('||'):
                one_more = True
                ops.append('||')
            elif self.skip_word('or'):
                one_more = True
                ops.append('or')
            if not one_more:
                break
            or_exprs.append(parse_and_expr(self))
        if len(or_exprs) == 1:
            return ASTRequiresClause(or_exprs[0])
        else:
            return ASTRequiresClause(ASTBinOpExpr(or_exprs, ops))

    def _parse_template_declaration_prefix(self, object_type: str,
                                           ) -> ASTTemplateDeclarationPrefix | None:
        templates: list[ASTTemplateParams | ASTTemplateIntroduction] = []
        while 1:
            self.skip_ws()
            # the saved position is only used to provide a better error message
            params: ASTTemplateParams | ASTTemplateIntroduction | None = None
            pos = self.pos
            if self.skip_word("template"):
                try:
                    params = self._parse_template_parameter_list()
                except DefinitionError as e:
                    if object_type == 'member' and len(templates) == 0:
                        return ASTTemplateDeclarationPrefix(None)
                    else:
                        raise e
                if object_type == 'concept' and params.requiresClause is not None:
                    self.fail('requires-clause not allowed for concept')
            else:
                params = self._parse_template_introduction()
                if not params:
                    break
            if object_type == 'concept' and len(templates) > 0:
                self.pos = pos
                self.fail("More than 1 template parameter list for concept.")
            templates.append(params)
        if len(templates) == 0 and object_type == 'concept':
            self.fail('Missing template parameter list for concept.')
        if len(templates) == 0:
            return None
        else:
            return ASTTemplateDeclarationPrefix(templates)

    def _check_template_consistency(self, nested_name: ASTNestedName,
                                    template_prefix: ASTTemplateDeclarationPrefix,
                                    full_spec_shorthand: bool, is_member: bool = False,
                                    ) -> ASTTemplateDeclarationPrefix:
        num_args = nested_name.num_templates()
        is_member_instantiation = False
        if not template_prefix:
            num_params = 0
        else:
            if is_member and template_prefix.templates is None:
                num_params = 0
                is_member_instantiation = True
            else:
                num_params = len(template_prefix.templates)
        if num_args + 1 < num_params:
            self.fail("Too few template argument lists compared to parameter"
                      " lists. Argument lists: %d, Parameter lists: %d."
                      % (num_args, num_params))
        if num_args > num_params:
            num_extra = num_args - num_params
            if not full_spec_shorthand and not is_member_instantiation:
                msg = (
                    f'Too many template argument lists compared to parameter lists. '
                    f'Argument lists: {num_args:d}, Parameter lists: {num_params:d}, '
                    f'Extra empty parameters lists prepended: {num_extra:d}. '
                    'Declaration:\n\t'
                )
                if template_prefix:
                    msg += f"{template_prefix}\n\t"
                msg += str(nested_name)
                self.warn(msg)

            new_templates: list[ASTTemplateParams | ASTTemplateIntroduction] = [
                ASTTemplateParams([], requires_clause=None)
                for _i in range(num_extra)
            ]
            if template_prefix and not is_member_instantiation:
                new_templates.extend(template_prefix.templates)
            template_prefix = ASTTemplateDeclarationPrefix(new_templates)
        return template_prefix

    def parse_declaration(self, objectType: str, directiveType: str) -> ASTDeclaration:
        object_type = objectType
        directive_type = directiveType
        if object_type not in {'class', 'union', 'function', 'member', 'type',
                              'concept', 'enum', 'enumerator'}:
            raise Exception('Internal error, unknown objectType "%s".' % object_type)
        if directive_type not in {'class', 'struct', 'union', 'function', 'member', 'var',
                                 'type', 'concept',
                                 'enum', 'enum-struct', 'enum-class', 'enumerator'}:
            raise Exception('Internal error, unknown directiveType "%s".' % directive_type)
        visibility = None
        template_prefix = None
        trailing_requires_clause = None
        declaration: Any = None

        self.skip_ws()
        if self.match(_visibility_re):
            visibility = self.matched_text

        if object_type in {'type', 'concept', 'member', 'function', 'class', 'union'}:
            template_prefix = self._parse_template_declaration_prefix(object_type)

        if object_type == 'type':
            prev_errors = []
            pos = self.pos
            try:
                if not template_prefix:
                    declaration = self._parse_type(named=True, outer='type')
            except DefinitionError as e:
                prev_errors.append((e, "If typedef-like declaration"))
                self.pos = pos
            pos = self.pos
            try:
                if not declaration:
                    declaration = self._parse_type_using()
            except DefinitionError as e:
                self.pos = pos
                prev_errors.append((e, "If type alias or template alias"))
                header = "Error in type declaration."
                raise self._make_multi_error(prev_errors, header) from e
        elif object_type == 'concept':
            declaration = self._parse_concept()
        elif object_type == 'member':
            declaration = self._parse_type_with_init(named=True, outer='member')
        elif object_type == 'function':
            declaration = self._parse_type(named=True, outer='function')
            trailing_requires_clause = self._parse_requires_clause()
        elif object_type == 'class':
            declaration = self._parse_class()
        elif object_type == 'union':
            declaration = self._parse_union()
        elif object_type == 'enum':
            declaration = self._parse_enum()
        elif object_type == 'enumerator':
            declaration = self._parse_enumerator()
        else:
            raise AssertionError
        template_prefix = self._check_template_consistency(declaration.name,
                                                          template_prefix,
                                                          full_spec_shorthand=False,
                                                          is_member=object_type == 'member')
        self.skip_ws()
        semicolon = self.skip_string(';')
        return ASTDeclaration(object_type, directive_type, visibility,
                              template_prefix, declaration,
                              trailing_requires_clause, semicolon)

    def parse_namespace_object(self) -> ASTNamespace:
        template_prefix = self._parse_template_declaration_prefix(object_type="namespace")
        name = self._parse_nested_name()
        template_prefix = self._check_template_consistency(name, template_prefix,
                                                          full_spec_shorthand=False)
        res = ASTNamespace(name, template_prefix)
        res.objectType = 'namespace'  # type: ignore[attr-defined]
        return res

    def parse_xref_object(self) -> tuple[ASTNamespace | ASTDeclaration, bool]:
        pos = self.pos
        try:
            template_prefix = self._parse_template_declaration_prefix(object_type="xref")
            name = self._parse_nested_name()
            # if there are '()' left, just skip them
            self.skip_ws()
            self.skip_string('()')
            self.assert_end()
            template_prefix = self._check_template_consistency(name, template_prefix,
                                                              full_spec_shorthand=True)
            res1 = ASTNamespace(name, template_prefix)
            res1.objectType = 'xref'  # type: ignore[attr-defined]
            return res1, True
        except DefinitionError as e1:
            try:
                self.pos = pos
                res2 = self.parse_declaration('function', 'function')
                # if there are '()' left, just skip them
                self.skip_ws()
                self.skip_string('()')
                self.assert_end()
                return res2, False
            except DefinitionError as e2:
                errs = []
                errs.append((e1, "If shorthand ref"))
                errs.append((e2, "If full function ref"))
                msg = "Error in cross-reference."
                raise self._make_multi_error(errs, msg) from e2

    def parse_expression(self) -> ASTExpression | ASTType:
        pos = self.pos
        try:
            expr = self._parse_expression()
            self.skip_ws()
            self.assert_end()
            return expr
        except DefinitionError as ex_expr:
            self.pos = pos
            try:
                typ = self._parse_type(False)
                self.skip_ws()
                self.assert_end()
                return typ
            except DefinitionError as ex_type:
                header = "Error when parsing (type) expression."
                errs = []
                errs.append((ex_expr, "If expression"))
                errs.append((ex_type, "If type"))
                raise self._make_multi_error(errs, header) from ex_type
